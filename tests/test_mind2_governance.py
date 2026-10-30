"""Security review regressions across quotation, privacy and graph authority."""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import pytest

from oomp.domain.graph import TemporalQuery
from oomp.domain.enums import MemoryStatus
from oomp.storage.graph_store import SQLiteGraphStore
from oomp.storage.memory_store import SQLiteMemoryStore
from oomp.storage.mind_projection_store import SQLiteMindProjectionStore
from oomp.understanding.contracts import ExtractionConfiguration
from oomp.understanding.engine import UnderstandingEngine
from oomp.understanding.rules import RulesExtractor, promotion
from test_mind2_acquisition import SCOPE, event, database


@pytest.mark.parametrize("text", [
    'Mara said: "I prefer tea. I plan to build a robot."',
    '"I prefer tea. My name is Fictional Cedar."',
    "'I prefer tea. I plan to build a robot.'",
    "\u201cI prefer tea. I plan to build a robot.\u201d",
    "\u2018I prefer tea. I plan to build a robot.\u2019",
    chr(96) * 3 + "\nI prefer tea.\nI plan to build a robot.\n" + chr(96) * 3,
    "~~~\nI prefer tea.\nI plan to build a robot.\n~~~",
    "> I prefer tea.\nI plan to build a robot.",
    "Mara said I prefer tea. I plan to build a robot.",
    '"I prefer tea. I plan to build a robot.',
])
def test_quoted_multiclause_and_code_cannot_be_promoted_after_segmentation(text):
    proposals = RulesExtractor().propose(SCOPE, event(text))
    assert proposals
    assert all(p.assertion_kind == "quoted" and promotion(p)[0] == "episodic-only" for p in proposals)


def test_real_declaration_after_closed_quote_and_contractions_remains_usable():
    sample = event('"A fictional statement." My name is Fictional Cedar.')
    proposals = RulesExtractor().propose(SCOPE, sample)
    assert proposals[-1].predicate == "alias" and promotion(proposals[-1])[0] == "canonical"
    assert promotion(RulesExtractor().propose(SCOPE, event("I don't prefer long replies."))[0])[0] == "canonical"


@pytest.mark.parametrize("text,kind", [
    ("If I move next year, I prefer Lahore and I plan to build a house.", "hypothetical"),
    ("Maybe I like tea and I plan to buy a teapot.", "uncertain"),
    ("Suppose I had more time;\nI plan to build a robot.", "hypothetical"),
])
def test_compound_clauses_keep_hypothetical_and_uncertain_context(text, kind):
    proposals = RulesExtractor().propose(SCOPE, event(text))
    assert len(proposals) == 2
    assert all(p.assertion_kind == kind and promotion(p)[0] == "episodic-only" for p in proposals)


@pytest.mark.parametrize("text", [
    "I like my diabetes treatment.", "I prefer the Liberal Party.",
    "I prefer my medication schedule.", "My religion is Christian.",
])
def test_common_sensitive_statements_are_excluded_or_consented_episode_only(text):
    sample = event(text)
    assert RulesExtractor().propose(SCOPE, sample) == ()
    retained = RulesExtractor(ExtractionConfiguration(sensitive_episodes=True)).propose(SCOPE, sample)
    assert retained and all(p.sensitivity == "sensitive" and promotion(p)[0] == "episodic-only" for p in retained)


@pytest.mark.parametrize("preexisting", [False, True])
def test_event_retraction_with_no_episodes_and_reused_legacy_ids_is_consistent(tmp_path, preexisting):
    from oomp.ingestion.pipeline import ExtractionPipeline
    sample = event("I prefer tea. I plan to build a robot.")
    path = database(tmp_path, sample)
    if preexisting:
        ExtractionPipeline(path).process_event(SCOPE, sample.event_id)
    result = UnderstandingEngine(path, ExtractionConfiguration(retain_episodes=False)).process_event(SCOPE, sample.event_id)
    assert len(result.processing.memory_ids) == 2
    before = datetime.now(timezone.utc)
    SQLiteMindProjectionStore(path).retract_source(SCOPE, result.processing.memory_ids[0], sample.event_id)
    graph = SQLiteGraphStore(path)
    assert all(graph.memory_state(SCOPE, i, TemporalQuery()).effective_status is MemoryStatus.RETRACTED
               for i in result.processing.memory_ids)
    assert all(graph.memory_state(SCOPE, i, TemporalQuery(known_at=before)).effective_status is MemoryStatus.ACTIVE
               for i in result.processing.memory_ids)


def test_withdrawn_episode_cannot_keep_a_protected_supersession_endorsed(tmp_path):
    from oomp.graph import GraphService
    from oomp.storage.errors import GraphConflictError
    from test_stage4_temporal import setup_hardware, SCOPE as hardware_scope, SEP20
    path, old, new, _, source = setup_hardware(tmp_path)
    acquisition = UnderstandingEngine(path).process_event(hardware_scope, source.event_id)
    episode_id = acquisition.processing.memory_ids[0]
    service = GraphService(path)
    proposal = service.propose_conflict(hardware_scope, new.memory_id, old.memory_id).proposal
    assert proposal is not None
    service.resolve(hardware_scope, proposal, confirm=True)
    before = datetime.now(timezone.utc)
    SQLiteMindProjectionStore(path).retract_source(hardware_scope, episode_id, source.event_id)
    graph = SQLiteGraphStore(path)
    assert graph.memory_state(hardware_scope, new.memory_id, TemporalQuery(valid_at=SEP20)).effective_status is MemoryStatus.RETRACTED
    assert graph.memory_state(hardware_scope, old.memory_id, TemporalQuery(valid_at=SEP20)).effective_status is MemoryStatus.ACTIVE
    assert graph.memory_state(hardware_scope, old.memory_id, TemporalQuery(valid_at=SEP20, known_at=before)).effective_status is MemoryStatus.SUPERSEDED
    with pytest.raises(GraphConflictError):
        service.resolve(hardware_scope, proposal, confirm=True)


def test_no_schema_migration_and_backup_reopen_preserve_episode_proofs(tmp_path):
    sample = event("My name is Fictional Cedar. What's your name?")
    path = database(tmp_path, sample)
    def schema(connection):
        return connection.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    with sqlite3.connect(path) as source:
        before = schema(source)
    result = UnderstandingEngine(path).process_event(SCOPE, sample.event_id)
    backup = tmp_path / "backup.sqlite3"
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        assert schema(source) == before
        assert source.execute("PRAGMA user_version").fetchone()[0] == 5
        source.backup(destination)
        assert schema(destination) == before
    reopened = SQLiteMemoryStore(backup)
    assert all(reopened.get(SCOPE, i).provenance == (sample.source_reference,) for i in result.processing.memory_ids)
