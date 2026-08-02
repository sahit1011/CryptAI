"""Consumer side of the shared signal plane.

The Rust signal engine (`signal-engine/`) publishes market pulses to Redis; this package
reads them. Nothing here computes market facts — that would defeat the point of the
shared plane, which is that the expensive analysis is paid for once.

See docs/MULTI_TENANCY.md for the boundary this package sits on.
"""
from src.signals.pulse_client import (
    Pulse,
    PulseClient,
    PulseIncompatible,
    PulseMissing,
    PulseStale,
    PulseUnavailable,
)

__all__ = [
    "Pulse",
    "PulseClient",
    "PulseIncompatible",
    "PulseMissing",
    "PulseStale",
    "PulseUnavailable",
]
