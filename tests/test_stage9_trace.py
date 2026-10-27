from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from benchmarks.contracts import Config
from benchmarks.datasets.generate import eligible,generate
from benchmarks.trace_compare import compare,fixture,trace_identity


def test_trace_fixture_ids_bind_actual_synthetic_interaction_and_user_role():
    d=generate(Config(name="trace-unit",seeds=(11,),sizes=(128,),categories=("long_history",)))
    owner,interactions,normalized,mapping=fixture(d.histories[0],d.cases[0])
    assert len(interactions)==len(normalized.events)==len(mapping)==128
    assert len({r["_id"] for r in interactions})==128
    for row,event in zip(interactions,normalized.events,strict=True):
        assert event.event_id==trace_identity(owner,row["_id"])
        assert event.source_reference.external_event_id==row["_id"]
        assert event.source_reference.turn_id=="trace-user-"+row["_id"]
        assert event.source_reference.source_system=="trace-ai"
        assert row["user_id"]==owner=="stage9-fictional-owner"


def test_trace_fixture_transform_preserves_content_scope_chronology_and_cutoff():
    d=generate(Config(name="trace-unit",seeds=(11,),sizes=(128,),categories=("long_history",)))
    h=d.histories[0];case=d.cases[0]
    owner,rows,transformed,mapping=fixture(h,case)
    assert [e.content for e in transformed.events]==[e.content for e in eligible(h,case)]
    assert [e.ingested_at for e in transformed.events]==[e.ingested_at for e in eligible(h,case)]
    assert {(e.tenant_id,e.namespace) for e in transformed.events}=={(h.tenant_id,h.namespace)}
    assert set(mapping)=={e.event_id for e in eligible(h,case)}


def test_missing_trace_environment_is_unavailable_without_creating_output(tmp_path):
    config=Config(name="trace-unit",seeds=(11,),sizes=(128,),categories=("long_history",))
    with pytest.raises(ValueError,match="unavailable"):compare(config,tmp_path/"no-trace",tmp_path/"output")
    assert not (tmp_path/"output").exists()
