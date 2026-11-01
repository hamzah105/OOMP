"""Read-only context selection around the existing canonical retrieval engine."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sqlite3
import time

from oomp.domain.enums import MemoryStatus, RelationshipType
from oomp.domain.graph import TemporalQuery
from oomp.domain.memories import SourceSpan
from oomp.domain.models import AuthorizedScope
from oomp.objects.contracts import ObjectMapError
from oomp.objects.queries import ReadContext
from oomp.objects.service import ObjectMap
from oomp.retrieval.contracts import RetrievalRequest
from oomp.retrieval.engine import RetrievalEngine, RetrievalUnavailableError
from oomp.storage.errors import StorageError, RetrievalIndexError, GraphLimitError, ScopeMismatchError
from oomp.storage.memory_store import _event_in_scope
from oomp.storage.graph_store import _valid_at
from oomp.storage.migrations import user_version
from oomp.storage.sqlite import _authorized, _timestamp
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.episodes import EPISODE_POLICY, episode_snapshot
from oomp.understanding.rules import blocked_reason, classify

from .contracts import ContextEvidence, ContextRequest, ContextResponse, ContextSource, ContextStatus, EvidenceResolution, RetrievalIntent
from .packing import pack_units, source_keys
from .planner import plan_request
from .navigation import associated_objects
from .validation import source_entails_memory

_TOPIC_PATTERNS = {
    'projects': re.compile(r'\bproject\b', re.I),
    'relocation': re.compile(r'\b(?:mov\w*|relocat\w*|cities|city|candidates|infrastructure)\b', re.I),
    'preferences': re.compile(r'\b(?:prefer\w*|response style)\b', re.I),
    'identity-claims': re.compile(r'\b(?:alias|name|called|call me)\b', re.I),
    'sensitive-discussion': re.compile(r'\b(?:politic\w*|leadership|prime minister|religio\w*)\b', re.I),
}
_GENERIC = frozenset('name names response style introduce introduced decide decided decision decisions plan plans now just previous earlier old original technical conversation topic question'.split())
_SENSITIVE_TRAIT = re.compile(r'\b(?:affiliation|nationality|ethnicity|ideology|allegiance|my religion|my political beliefs|which party)\b', re.I)


class _Stopped(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _IncompleteConflict(Exception):
    pass


class _SummaryNotSelected(Exception):
    pass


class _Objects(ObjectMap):
    def __init__(self, path, session):
        super().__init__(path)
        self.session = session

    def _memory_state_in_connection(self, connection, scope, memory_id, query):
        if connection is not self.session._connection or scope != self.session.scope:
            raise ScopeMismatchError('context_object_snapshot_mismatch')
        return self.session.memory_state(memory_id, query)


def _stem(word):
    word = word.casefold().removesuffix("'s")
    for prefix in ('relocat', 'mov', 'prefer', 'politic', 'project', 'alias'):
        if word.startswith(prefix):
            return prefix
    return word


def _relevant(quote, plan):
    if plan.topic_hints:
        return any(_TOPIC_PATTERNS[topic].search(quote) for topic in plan.topic_hints if topic in _TOPIC_PATTERNS)
    focus = {_stem(word) for word in plan.focus_terms if word not in _GENERIC}
    words = {_stem(word) for word in re.findall(r"[^\W_]+(?:'s)?", quote, re.UNICODE)}
    return bool(focus & words) or any(anchor.casefold() in quote.casefold() for anchor in plan.anchors)


def _claim_relevant(quote, plan, fields, memory):
    """A project's name is not a person's claimed alias.

    Called only after independent source entailment. P2.1 literal refinements
    may be more specific than the rules classifier; their fields have already
    been re-proved by the literal validator, not trusted as arbitrary metadata.
    """
    if 'identity-claims' not in plan.topic_hints:
        return _relevant(quote, plan)
    alias = fields['predicate'] == 'alias' and fields['memory_category'] == 'profile'
    alias |= (memory.metadata.get('canonicalization_version') == 'p2.1'
              and memory.metadata.get('predicate') == 'alias'
              and memory.metadata.get('category') == 'profile')
    return any(alias if topic == 'identity-claims' else
               bool(_TOPIC_PATTERNS[topic].search(quote))
               for topic in plan.topic_hints if topic in _TOPIC_PATTERNS)


def _identity(*values):
    return 'ctx-' + hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


class ContextEngine:
    """One scoped snapshot, one existing ranker, finite derived evidence units.

    Cancellation is cooperative between bounded operations; it cannot guarantee
    immediate cancellation of a configured provider's blocked system call.
    """
    def __init__(self, path=None, *, provider=None, deadline_seconds=5.0, clock=time.monotonic, cancelled=None):
        if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 15:
            raise ValueError('invalid_context_deadline')
        self.path = path
        self.base = RetrievalEngine(path, provider=provider)
        self.deadline_seconds = float(deadline_seconds)
        self.clock = clock
        self.cancelled = cancelled

    def retrieve(self, scope: AuthorizedScope, request: ContextRequest) -> ContextResponse:
        scope = _authorized(scope)
        if not isinstance(request, ContextRequest):
            raise TypeError('validated_context_request_required')
        request = ContextRequest.model_validate(request.model_dump(mode='json'))
        if (scope.tenant_id, scope.namespace) != (request.tenant_id, request.namespace):
            raise ScopeMismatchError('context_scope_mismatch')
        plan = plan_request(request)
        reasons = list(plan.reasons)
        trace = {}
        started = self.clock()

        def check():
            try:
                cancelled = self.cancelled is not None and self.cancelled()
            except Exception:
                raise _Stopped('context_cancellation_failed') from None
            if cancelled:
                raise _Stopped('context_cancelled')
            if self.clock() - started >= self.deadline_seconds:
                raise _Stopped('context_deadline')

        def response(status, *, packed=None, degraded=False, coverage='unknown'):
            units = packed.evidence_packets if packed else ()
            return ContextResponse(retrieval_intent=plan.retrieval_intent, retrieval_status=status,
                evidence_packets=units,
                source_references=tuple(dict.fromkeys(p.source_reference for u in units for p in u.source_proofs)),
                context_packet=packed.context_packet if packed else '',
                selected_context_bytes=packed.selected_context_bytes if packed else 0,
                token_budget=request.token_budget, degraded=degraded,
                reasons=tuple(dict.fromkeys(reasons))[:32], coverage=coverage, trace=trace,
                query_plan=plan if request.explain else None)

        try:
            check()
            if not plan.search_allowed:
                return response(ContextStatus.UNCERTAIN if plan.needs_clarification else ContextStatus.NOT_FOUND)
            if 'sensitive-discussion' in plan.topic_hints and _SENSITIVE_TRAIT.search(request.query):
                reasons.append('topic_does_not_establish_personal_trait')
                return response(ContextStatus.UNCERTAIN)
            # Query variants share one bounded disjunction and one existing
            # lexical/semantic/entity/topic ranking pass, not three scans.
            terms = tuple(dict.fromkeys(word for variant in plan.query_variants for word in re.findall(r'[^\W_]+', variant, re.UNICODE)))[:32]
            query_text = ' '.join(terms)[:4096]
            historical = request.historical or plan.retrieval_intent is RetrievalIntent.HISTORICAL_CORRECTION
            valid_at = request.effective_valid_at
            if valid_at is None and not historical:
                valid_at = datetime.now(timezone.utc)
            temporal = TemporalQuery(known_at=request.known_at, valid_at=valid_at)
            incoming = RetrievalRequest(tenant_id=scope.tenant_id, namespace=scope.namespace,
                query=query_text, max_results=100, token_budget=32768, mode=request.mode,
                allow_degraded=request.allow_degraded, candidate_limit=request.candidate_limit,
                min_semantic_similarity=request.min_semantic_similarity,
                known_at=request.known_at, valid_at=valid_at, historical=historical,
                graph_depth=request.graph_depth, graph_nodes=request.graph_nodes,
                graph_edges=request.graph_edges, graph_work=request.graph_work,
                graph_relationships=request.graph_relationships)
            embedding = self.base._prepare_embedding(incoming)
            check()
            with self.base.store.read_snapshot(scope, principal_only=True) as session:
                if session.scope != scope or not session.principal_only:
                    raise ScopeMismatchError('context_principal_snapshot_required')
                c = session._connection
                if user_version(c) != 6:
                    reasons.append('context_requires_schema_v6')
                    return response(ContextStatus.UNAVAILABLE)
                stopped = []

                def progress():
                    try:
                        check()
                        return 0
                    except _Stopped as error:
                        stopped.append(error.code)
                        return 1

                c.set_progress_handler(progress, 1000)
                try:
                    objects = _Objects(self.path, session)
                    extra_ids, object_rows, associated = self._object_candidates(session, objects, scope, plan, temporal, request, trace, check)
                    index = session.index_status(embedding[1])
                    coverage = 'complete'
                    if index.lexical_stale:
                        reasons.append('lexical_index_incomplete')
                        return response(ContextStatus.INDEX_INCOMPLETE, coverage='partial')
                    selected = []
                    # One optional graph domain per request: an explicitly
                    # anchored P3 walk or the legacy canonical graph, never
                    # multiplied independent hop/work budgets.
                    ranked_request = incoming.model_copy(update={'graph_depth':0}) if trace.get('p3_graph_lane',0) else incoming
                    legacy = self.base._retrieve(scope, ranked_request, _session=session,
                        _embedding_state=embedding, _extra_lanes={'topic': extra_ids},
                        _candidate_sink=selected)
                    check()
                    reasons.extend(legacy.warnings)
                    trace.update({key: value for key, value in legacy.retrieval_trace.model_dump().items() if type(value) is int})
                    if legacy.degraded:
                        coverage = 'partial'
                    units, upgrades = self._units(session, objects, scope, selected, object_rows, plan, temporal, request, reasons, trace, check, associated=associated)
                    if trace.get('p3_association_truncated',0):
                        reasons.append('p3_association_expansion_incomplete')
                        coverage = 'partial'
                    if trace.get('object_candidate_truncated',0) or trace.get('object_invalid',0):
                        reasons.append('object_candidate_coverage_incomplete')
                        coverage = 'partial'
                    if legacy.retrieval_trace.graph_truncated:
                        trace['canonical_graph_truncated'] = 1
                        reasons.append('canonical_graph_expansion_incomplete')
                        coverage = 'partial'
                    if trace.get('summary_invalid',0):
                        reasons.append('episode_summary_coverage_incomplete')
                        coverage = 'partial'
                    if trace.get('summary_candidate_truncated',0):
                        reasons.append('episode_summary_search_incomplete')
                        coverage = 'partial'
                    if trace.get('projection_unavailable', 0):
                        reasons.append('object_projection_coverage_unknown')
                        coverage = 'partial'
                    packed = pack_units(units, request.token_budget, request.max_results, upgrades=upgrades)
                    check()
                    trace.update(context_candidates=len(units), context_packed=len(packed.evidence_packets),
                                 context_budget_dropped=packed.dropped, context_expanded=packed.expanded)
                    if packed.dropped:
                        reasons.append('whole_evidence_excluded_by_budget_or_result_limit')
                    if packed.evidence_packets:
                        uncertain = any(u.temporal_status in {'contradicted', 'tentative', 'correction_pending'}
                                        or 'tentative' in u.assertion_kinds for u in packed.evidence_packets)
                        return response(ContextStatus.UNCERTAIN if uncertain else ContextStatus.FOUND,
                                        packed=packed, degraded=legacy.degraded, coverage=coverage)
                    if units:
                        return response(ContextStatus.BUDGET_EXCLUDED, packed=packed, degraded=legacy.degraded, coverage=coverage)
                    if trace.get('uncertain_withheld', 0):
                        return response(ContextStatus.UNCERTAIN, degraded=legacy.degraded, coverage=coverage)
                    return response(ContextStatus.NOT_FOUND if coverage == 'complete' else ContextStatus.INDEX_INCOMPLETE,
                                    degraded=legacy.degraded, coverage=coverage)
                finally:
                    c.set_progress_handler(None, 0)
                    if stopped:
                        raise _Stopped(stopped[0])
        except _Stopped as error:
            reasons.append(error.code)
            return response(ContextStatus.UNAVAILABLE, degraded=True)
        except _IncompleteConflict:
            reasons.append('complete_conflict_bundle_unavailable')
            trace['uncertain_withheld'] = 1
            return response(ContextStatus.UNCERTAIN, coverage='partial')
        except RetrievalIndexError:
            reasons.append('context_index_incomplete')
            return response(ContextStatus.INDEX_INCOMPLETE, degraded=True, coverage='partial')
        except GraphLimitError:
            reasons.append('context_graph_limit')
            return response(ContextStatus.INDEX_INCOMPLETE, degraded=True, coverage='partial')
        except RetrievalUnavailableError:
            reasons.append('configured_semantic_lane_unavailable')
            return response(ContextStatus.UNAVAILABLE, degraded=True)
        except (StorageError, sqlite3.Error):
            reasons.append('context_storage_unavailable')
            return response(ContextStatus.UNAVAILABLE, degraded=True)
        except (ObjectMapError, ValueError):
            reasons.append('context_evidence_validation_failed')
            return response(ContextStatus.INDEX_INCOMPLETE, degraded=True, coverage='partial')

    def _object_candidates(self, session, objects, scope, plan, temporal, request, trace, check):
        c = session._connection
        predicate, values = session._memory_predicate('m')
        conditions = []
        parameters = [scope.tenant_id, scope.namespace, scope.principal_id]
        if plan.anchors:
            conditions.append('p.label IN (' + ','.join('?' for _ in plan.anchors) + ')')
            parameters.extend(plan.anchors)
        kinds = []
        if 'projects' in plan.topic_hints: kinds.append('project')
        if 'relocation' in plan.topic_hints: kinds.extend(('plan', 'place', 'concept'))
        if 'identity-claims' in plan.topic_hints: kinds.append('person')
        if kinds:
            conditions.append('o.object_type IN (' + ','.join('?' for _ in kinds) + ')')
            parameters.extend(kinds)
        if not conditions:
            return (), (), frozenset()
        sql = '''SELECT DISTINCT p.object_id FROM map_proofs p JOIN map_objects o
                 ON o.tenant_id=p.tenant_id AND o.namespace=p.namespace AND o.principal_id=p.principal_id AND o.object_id=p.object_id
                 JOIN memories m ON m.tenant_id=p.tenant_id AND m.namespace=p.namespace AND m.memory_id=p.memory_id
                 WHERE p.tenant_id=? AND p.namespace=? AND p.principal_id=? AND (''' + ' OR '.join(conditions) + ') AND (' + predicate + ')'
        parameters.extend(values)
        if temporal.known_at is not None:
            sql += ' AND p.recorded_at<=?'
            parameters.append(_timestamp(temporal.known_at))
        rows = c.execute(sql + ' ORDER BY p.object_id LIMIT 9', parameters).fetchall()
        if len(rows) > 8:
            trace['object_candidate_truncated'] = 1
        ctx = ReadContext(temporal, maximum=2000)
        found = []
        ids = []
        for row in rows[:8]:
            check()
            try:
                obj = objects._get(c, scope, row[0], ctx)
            except ObjectMapError:
                trace['object_invalid'] = trace.get('object_invalid', 0) + 1
                continue
            if obj is None:
                continue
            found.append(obj)
            for proof in reversed(obj.source_proofs):
                if session.owns_memory(proof.memory_id) and _relevant(proof.source_span.quote, plan) and proof.memory_id not in ids:
                    ids.append(proof.memory_id)
        trace['object_examined'] = ctx.budget.used
        linked, stats, graph_lane = associated_objects(objects,session,scope,tuple(found),plan,temporal,request,check)
        trace.update(stats)
        if graph_lane:
            trace['p3_graph_lane'] = 1
        related = set()
        for obj in linked:
            found.append(obj)
            for proof in obj.source_proofs:
                if session.owns_memory(proof.memory_id):
                    related.add(proof.memory_id)
                    if proof.memory_id not in ids:
                        ids.append(proof.memory_id)
        return tuple(ids[:request.candidate_limit]), tuple(found), frozenset(related)

    def _proofs(self, session, scope, memory_id, temporal, request, plan, *, relevant=True):
        memory = session.memory(memory_id)
        if memory is None:
            return None
        state = session.memory_state(memory_id, temporal)
        if state.known is not True or not state.evidence or state.valid is False:
            return None
        if len(state.source_event_ids) > 16:
            return None
        historical = request.historical or plan.retrieval_intent is RetrievalIntent.HISTORICAL_CORRECTION
        if state.effective_status is MemoryStatus.RETRACTED or (state.effective_status is MemoryStatus.SUPERSEDED and not historical):
            return None
        c = session._connection
        proofs = []
        assertions = []
        correction = False
        for identifier in state.source_event_ids:
            if not session.owns_event(identifier):
                return None
            event = _event_in_scope(c, scope, identifier)
            row = c.execute('SELECT source_span_json FROM memory_sources WHERE tenant_id=? AND namespace=? AND memory_id=? AND event_id=?',
                            (scope.tenant_id, scope.namespace, memory_id, identifier)).fetchone()
            if row is None or row[0] is None:
                return None
            span = SourceSpan.model_validate_json(row[0])
            if event is None or event.content[span.start:span.end] != span.quote:
                raise ValueError('context_source_span_invalid')
            if blocked_reason(scope, event, ExtractionConfiguration()) is not None:
                return None
            if not source_entails_memory(scope, event, span, memory):
                return None
            fields = classify(event, span)
            if fields['assertion_kind'] in {'hypothetical', 'quoted', 'question', 'assistant-originated'}:
                if not re.search(r'\b(?:hypothetical|quoted|question|assistant)\b', request.query, re.I):
                    return None
            if fields['sensitivity'] == 'sensitive' and 'sensitive-discussion' not in plan.topic_hints:
                return None
            if relevant and not _claim_relevant(span.quote, plan, fields, memory):
                return None
            assertions.append(fields['assertion_kind'])
            correction |= fields['predicate'] == 'correction' or bool(re.search(r'\b(?:changed my mind|decided not|not going to|no longer)\b', span.quote, re.I))
            proofs.append(ContextSource(memory_id=memory_id, event_id=identifier, source_reference=event.source_reference,
                span_start=span.start, span_end=span.end, quote=span.quote if request.include_source_content else None))
        if not proofs or len(proofs) > 16:
            return None
        return memory, tuple(proofs), tuple(dict.fromkeys(assertions)), correction

    def _units(self, session, objects, scope, selected, object_rows, plan, temporal, request, reasons, trace, check, *, associated=frozenset()):
        c = session._connection
        eligible = {}
        for evidence in selected:
            check()
            proof = self._proofs(session, scope, evidence.memory_id, temporal, request, plan,
                                 relevant=evidence.memory_id not in associated)
            if proof is not None:
                eligible[evidence.memory_id] = (evidence, proof)
        trace['context_relevant_memories'] = len(eligible)
        # Include both ends of an endorsed dispute as one atomic evidence unit.
        groups = []
        blocked = set()
        conflict_work = 0
        for identifier, (evidence, _) in tuple(eligible.items()):
            if identifier in blocked or evidence.temporal_status != 'contradicted':
                continue
            ids = {identifier}
            queue = [identifier]
            while queue:
                check()
                current = queue.pop()
                remaining = request.graph_work - conflict_work
                if remaining <= 0:
                    raise _IncompleteConflict()
                try:
                    records = session.neighbors(current,
                        allowed_relationships=(RelationshipType.CONTRADICTS,),
                        known_at=temporal.known_at, limit=min(20, remaining))
                except StorageError:
                    raise _IncompleteConflict() from None
                conflict_work += len(records)
                for record in records:
                    edge = record.edge
                    if _valid_at(edge.valid_from, edge.valid_until, temporal.valid_at) is False:
                        continue
                    other = edge.target_node_id if edge.source_node_id == current else edge.source_node_id
                    if other not in ids:
                        ids.add(other)
                        queue.append(other)
                    if len(ids) > 16:
                        raise _IncompleteConflict()
            members = []
            for member in sorted(ids):
                proof = self._proofs(session, scope, member, temporal, request, plan, relevant=False)
                if proof is None:
                    break
                members.append(proof)
            blocked.update(ids)
            if len(members) != len(ids) or sum(len(p[1]) for p in members) > 16:
                raise _IncompleteConflict()
            groups.append(self._bundle(members, resolution=EvidenceResolution.CANONICAL_FACT,
                                       temporal_status='contradicted', selection_reasons=('governed_conflict_bundle',), score=evidence.retrieval_score))
        blocked_keys = {(p.event_id, p.span_start, p.span_end) for mid in blocked
                        for p in (self._proofs(session, scope, mid, temporal, request, plan, relevant=False) or (None, (), (), False))[1]}
        leaves = []
        for identifier, (evidence, proof) in eligible.items():
            if identifier in blocked or any((p.event_id, p.span_start, p.span_end) in blocked_keys for p in proof[1]):
                continue
            unit = self._bundle([proof], temporal_status='correction_pending' if proof[3] else ('tentative' if 'tentative' in proof[2] else evidence.temporal_status),
                                selection_reasons=evidence.selection_reasons, score=evidence.retrieval_score)
            leaves.append((proof[3], unit))
        # Explicit correction evidence is preferred, without creating a
        # supersession or pretending an undecided plan was completed.
        leaves.sort(key=lambda value: (not value[0], -(value[1].retrieval_score or 0), value[1].unit_id))
        coarse = []
        upgrades = []
        object_memory = set()
        for obj in object_rows:
            check()
            members = []
            seen = set()
            for p in obj.source_proofs:
                if p.memory_id in seen or p.memory_id not in eligible or p.memory_id in blocked:
                    continue
                proof = eligible[p.memory_id][1]
                if any((s.event_id, s.span_start, s.span_end) in blocked_keys for s in proof[1]):
                    continue
                seen.add(p.memory_id)
                members.append(proof)
            if not members or sum(len(m[1]) for m in members) > 16:
                continue
            # Object labels/aliases/status were derived from ALL admitted P3
            # source assertions. Never retain a newer label after excluding its
            # source; fall back to the individually proven canonical claims.
            admitted = {(p.event_id, p.span_start, p.span_end) for m in members for p in m[1]}
            if not {(p.event_id, p.source_span.start, p.source_span.end) for p in obj.source_proofs} <= admitted:
                continue
            detailed = self._bundle(members, object_ids=(obj.object_id,), temporal_status=obj.status,
                                    selection_reasons=('source_backed_object',))
            content = json.dumps({'type':obj.object_type.value,'label':obj.canonical_label,'aliases':list(obj.aliases),'status':obj.status}, ensure_ascii=False, separators=(',', ':'))
            coarse.append(detailed.model_copy(update={'resolution':EvidenceResolution.OBJECT_SNAPSHOT, 'content':content, 'derived':True}))
            upgrades.append(detailed)
            object_memory.update(detailed.memory_ids)
        summaries = []
        if eligible:
            placeholders = ','.join('?' for _ in eligible)
            topics = c.execute('SELECT DISTINCT topic_id FROM topic_memberships WHERE tenant_id=? AND namespace=? AND memory_id IN ('+placeholders+') ORDER BY topic_id LIMIT 9',
                               (scope.tenant_id,scope.namespace,*eligible)).fetchall()
            if len(topics) > 8:
                trace['summary_candidate_truncated'] = 1
            for topic in topics[:8]:
                check()
                sql = 'SELECT * FROM mind_summary_revisions WHERE tenant_id=? AND namespace=? AND topic_id=? AND policy_version=?'
                args = [scope.tenant_id,scope.namespace,topic[0],EPISODE_POLICY]
                if temporal.known_at is not None:
                    sql += ' AND recorded_at<=? AND (retired_at IS NULL OR retired_at>?)'
                    args.extend((_timestamp(temporal.known_at),_timestamp(temporal.known_at)))
                else:
                    sql += ' AND retired_at IS NULL'
                revision = c.execute(sql+' ORDER BY revision_number DESC LIMIT 1',args).fetchone()
                if revision is None:
                    continue
                try:
                    memories, content, fingerprint = episode_snapshot(objects,c,scope,topic[0],known_at=temporal.known_at)
                    if revision['source_fingerprint'] != fingerprint or revision['content'] != content:
                        raise ValueError('stale_summary')
                    manifest = c.execute('SELECT memory_id,event_id FROM mind_summary_sources WHERE tenant_id=? AND namespace=? AND revision_id=? LIMIT 17',
                                         (scope.tenant_id,scope.namespace,revision['revision_id'])).fetchall()
                    expected = {(m.memory_id,event_id) for m in memories for event_id in m.source_event_ids}
                    if len(manifest) > 16 or {tuple(row) for row in manifest} != expected:
                        raise ValueError('summary_manifest_mismatch')
                    members = []
                    for memory in memories:
                        proof = self._proofs(session,scope,memory.memory_id,temporal,request,plan)
                        if proof is None or any((p.event_id,p.span_start,p.span_end) in blocked_keys for p in proof[1]):
                            raise _SummaryNotSelected()
                        members.append(proof)
                    if members:
                        summaries.append(self._bundle(members,resolution=EvidenceResolution.EPISODE_SUMMARY,
                            content=content,revision_id=revision['revision_id'],source_fingerprint=fingerprint,
                            selection_reasons=('validated_extractive_summary',)))
                except _SummaryNotSelected:
                    trace['summary_excluded'] = trace.get('summary_excluded',0)+1
                    trace['summary_not_selected'] = trace.get('summary_not_selected',0)+1
                    reasons.append('summary_support_stale_or_not_relevant')
                except (ValueError, ObjectMapError):
                    trace['summary_excluded'] = trace.get('summary_excluded',0)+1
                    reasons.append('summary_support_stale_or_not_relevant')
                    trace['summary_invalid'] = trace.get('summary_invalid',0)+1
        if eligible and not c.execute('SELECT 1 FROM map_proofs WHERE tenant_id=? AND namespace=? AND principal_id=? LIMIT 1',
                                     (scope.tenant_id,scope.namespace,scope.principal_id)).fetchone():
            trace['projection_unavailable'] = 1
        factual = plan.retrieval_intent in {RetrievalIntent.FACTUAL_RECALL,RetrievalIntent.ENTITY_LOOKUP,RetrievalIntent.HISTORICAL_CORRECTION}
        candidates = [*groups, *(unit for _,unit in leaves)] if factual else [*groups,*summaries,*coarse,*(unit for _,unit in leaves)]
        if factual:
            # Leaf facts answer precise lookups; compact object alternatives can
            # still fit when a whole canonical record would exceed the budget.
            candidates.extend(coarse)
        if request.include_source_content:
            for unit in (*candidates,*upgrades):
                raw = '\n'.join(p.quote for p in unit.source_proofs if p.quote is not None)
                if raw:
                    upgrades.append(unit.model_copy(update={'resolution':EvidenceResolution.SOURCE_EVIDENCE,'content':raw,'derived':False}))
        return tuple(candidates[:240]), tuple(upgrades[:240])

    @staticmethod
    def _bundle(members, *, resolution=EvidenceResolution.CANONICAL_FACT, content=None, object_ids=(), revision_id=None, source_fingerprint=None,
                temporal_status='uncertain', selection_reasons=(), score=None):
        proofs = []
        seen = set()
        for member in members:
            for proof in member[1]:
                key = (proof.event_id,proof.span_start,proof.span_end)
                if key not in seen:
                    seen.add(key)
                    proofs.append(proof)
        memories = tuple(dict.fromkeys(p.memory_id for p in proofs))
        by_id = {member[0].memory_id:member for member in members}
        if content is None:
            content = '\n'.join(by_id[mid][0].canonical_content for mid in memories)
        assertions = tuple(dict.fromkeys(kind for mid in memories for kind in by_id[mid][2]))
        if temporal_status == 'uncertain' and 'tentative' in assertions:
            temporal_status = 'tentative'
        return ContextEvidence(unit_id=_identity(resolution.value,memories,revision_id,object_ids),resolution=resolution,
            content=content,memory_ids=memories,source_proofs=tuple(proofs),object_ids=object_ids,
            revision_id=revision_id,source_fingerprint=source_fingerprint,assertion_kinds=assertions,
            temporal_status=temporal_status,selection_reasons=tuple(dict.fromkeys(selection_reasons))[:16],retrieval_score=score,
            derived=resolution in {EvidenceResolution.OBJECT_SNAPSHOT,EvidenceResolution.EPISODE_SUMMARY},uncertain=True)
