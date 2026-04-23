"""Abstract adapter interface for realtime vehicle position sources — Phase 2 Step 3.

Every realtime source (IETT SOAP, simulated metro, simulated ferry, etc.)
subclasses BaseAdapter so the Celery task pipeline can poll them uniformly.
Concrete adapters own their own retry and rate-limit logic internally —
callers treat fetch() as a single synchronous snapshot.

The ``source`` and ``mode`` fields are adapter-level constants: each adapter
yields one transit mode (IETT → "bus", metro sim → "metro", ferry sim →
"ferry"). If a future feed mixes modes, that adapter can override ``mode``
per-VehiclePosition inside fetch() — the class-level attribute is a default
and a documentation anchor, not a hard enforcement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from apps.realtime.schemas import VehiclePosition


class BaseAdapter(ABC):
    """Contract for any realtime vehicle position source."""

    name: ClassVar[str]
    source: ClassVar[str]
    mode: ClassVar[str]

    @abstractmethod
    def fetch(self) -> list[VehiclePosition]:
        """Return a single snapshot of current vehicle positions.

        Implementations handle their own rate limiting, retries, and
        transient error recovery. A failure to reach the upstream should
        either raise (caller decides) or return an empty list — never a
        partial set with silently-dropped vehicles.
        """

    def health(self) -> dict:
        """Lightweight status signal for monitoring / admin endpoints.

        Subclasses may override to surface rate-limit remaining, last
        successful fetch timestamp, upstream latency, etc.
        """
        return {"adapter": self.name, "healthy": True}
