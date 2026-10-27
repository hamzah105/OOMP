"""Evaluation-only adapters. No production service is patched or copied."""
from typing import Protocol

from benchmarks.contracts import Case, Result


class MemoryAdapter(Protocol):
    """Future external adapters must retain scope, cutoff, budget and raw proof.

    Construction accepts the same frozen Prepared corpus plus explicit settings.
    Cloud/service calls require a separately provisioned opt-in configuration.
    """
    def retrieve(self, case: Case) -> Result: ...
