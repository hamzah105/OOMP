from __future__ import annotations

from datetime import timedelta

import pytest

from benchmarks.contracts import Config, Dataset, digest
from benchmarks.datasets.generate import eligible, generate, validate


def config(**kw):
    return Config(name="test",seeds=(17,),sizes=(16,),evidence_budget=12000,summary_budget=12000,**kw)


def test_dataset_determinism_and_stable_ids():
    a,b=generate(config()),generate(config())
    assert a.model_dump_json()==b.model_dump_json()
    assert digest(a.model_dump(mode="json"))==digest(b.model_dump(mode="json"))
    assert len({c.case_id for c in a.cases})==len(a.cases)==20


def test_ground_truth_is_actual_eligible_source_evidence():
    dataset=generate(config()); histories={h.history_id:h for h in dataset.histories}
    for case in dataset.cases:
        sources={e.event_id:e for e in eligible(histories[case.history_id],case)}
        assert set(case.relevant_source_event_ids)<=set(sources)
        assert all(sources[s].source_reference.external_event_id==s for s in case.relevant_source_event_ids)


def test_latest_eight_positive_and_old_negative_controls():
    cases=generate(config()).cases
    assert next(c for c in cases if c.case_id.endswith("-recent")).latest_eight_available
    assert not next(c for c in cases if c.case_id.endswith("-old-direct")).latest_eight_available


def test_long_demonstration_over_100_later_interactions():
    d=generate(Config(name="demo",seeds=(11,),sizes=(128,),categories=("long_history",)))
    c=d.cases[0]
    assert c.fact_distance==127 and len(d.histories[0].events)==128
    assert not c.latest_eight_available


def test_seeds_change_entities_values_and_source_ids():
    a,b=generate(config()),generate(Config(name="test",seeds=(19,),sizes=(16,)))
    assert {h.history_id for h in a.histories}.isdisjoint(h.history_id for h in b.histories)
    assert a.histories[0].events[0].content!=b.histories[0].events[0].content


def test_split_entities_source_ids_and_project_query_templates_are_disjoint():
    datasets=[generate(Config(name="test",seeds=(17,),sizes=(16,),split=s)) for s in ("development","validation","heldout")]
    for i,a in enumerate(datasets):
        for b in datasets[i+1:]:
            assert {h.history_id for h in a.histories}.isdisjoint(h.history_id for h in b.histories)
            assert a.histories[0].events[0].content!=b.histories[0].events[0].content
            assert a.cases[0].query!=b.cases[0].query


def test_recorded_cutoff_differs_from_late_event_occurrence_time():
    d=generate(config()); h=next(h for h in d.histories if h.category=="temporal")
    late=next(e for e in h.events if "ArchiveUnit" in e.content)
    c=next(c for c in d.cases if c.history_id==h.history_id and c.known_at)
    assert late.occurred_at<c.known_at<late.ingested_at
    assert late.event_id not in {e.event_id for e in eligible(h,c)}


@pytest.mark.parametrize("suffix",["-future","-foreign","-excluded"])
def test_negative_controls_cannot_index_forbidden_sources(suffix):
    d=generate(config()); c=next(c for c in d.cases if c.case_id.endswith(suffix));h=next(h for h in d.histories if h.history_id==c.history_id)
    assert not set(c.forbidden_source_event_ids)&{e.event_id for e in eligible(h,c)}


def test_invalid_future_ground_truth_is_rejected():
    d=generate(config());c=next(c for c in d.cases if c.case_id.endswith("-future"))
    bad=c.model_copy(update={"relevant_source_event_ids":c.forbidden_source_event_ids,"answerability":"answerable","expected_answers":("silver",)})
    with pytest.raises(ValueError,match="future"):validate(d.model_copy(update={"cases":(bad,)}))


def test_duplicate_case_and_source_rejection():
    d=generate(config())
    with pytest.raises(ValueError,match="duplicate"):validate(d.model_copy(update={"cases":(*d.cases,d.cases[0])}))
    h=d.histories[0]
    with pytest.raises(ValueError,match="duplicate"):validate(d.model_copy(update={"histories":(h.model_copy(update={"events":(*h.events,h.events[0])}),)}))


def test_missing_source_label_is_rejected():
    d=generate(config());c=d.cases[0].model_copy(update={"relevant_source_event_ids":("invented-source",)})
    with pytest.raises(ValueError,match="missing"):validate(d.model_copy(update={"cases":(c,)}))


def test_invented_path_is_rejected():
    d=generate(config());c=d.cases[0].model_copy(update={"required_chain":(("made-up","also-fake"),),"required_hops":1})
    with pytest.raises(ValueError,match="invented"):validate(d.model_copy(update={"cases":(c,)}))


def test_unknown_validity_is_not_filled_for_text_only_sources():
    d=generate(config());h=d.histories[0]
    assert h.curated==()
    assert all(e.metadata.get("valid_from") is None for e in h.events)


@pytest.mark.parametrize("changes",[
    {"methods":("unknown",)}, {"methods":()}, {"seeds":(1,1)}, {"sizes":(17,)},
    {"graph_depth":3},{"summary_budget":15000},{"prompt_budget":32768,"num_ctx":8192},
])
def test_invalid_preregistration_is_rejected(changes):
    kw={"name":"test","seeds":(17,),"sizes":(16,),"evidence_budget":12000,"summary_budget":12000,**changes}
    with pytest.raises(ValueError):Config(**kw)


def test_workload_limits_fail_instead_of_silent_truncation():
    with pytest.raises(ValueError,match="workload"):generate(config(max_cases=1))


def test_frozen_dataset_json_roundtrip_and_digest():
    d=generate(config());copy=Dataset.model_validate_json(d.model_dump_json())
    assert digest(d.model_dump(mode="json"))==digest(copy.model_dump(mode="json"))
    with pytest.raises(ValueError):d.version="another-version"
