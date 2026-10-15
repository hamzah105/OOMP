from __future__ import annotations

import pytest

from oomp.retrieval.fusion import fuse_ranked


def test_rrf_merges_duplicate_ids_without_mixing_raw_scores():
    ranked = fuse_ranked({
        "lexical": ("mem-a", "mem-b", "mem-a"),
        "semantic": ("mem-b", "mem-a"),
        "entity": ("mem-a",),
    })
    assert [item.memory_id for item in ranked] == ["mem-a", "mem-b"]
    assert ranked[0].reasons == ("lexical", "semantic", "entity")
    assert ranked[0].score > ranked[1].score > 0


def test_rrf_ties_are_stable_and_input_validation_is_bounded():
    assert [item.memory_id for item in fuse_ranked({"lexical": ("mem-z", "mem-a"), "semantic": ("mem-a", "mem-z")})] == ["mem-a", "mem-z"]
    with pytest.raises(ValueError):
        fuse_ranked({"unknown": ("mem-a",)})
    with pytest.raises(ValueError):
        fuse_ranked({"lexical": tuple("mem-" + str(i) for i in range(201))})