"""Event-driven scenario engine with information asymmetry enforcement.

An Event represents something that happens in the network at a specific time slot.
Events have an 'audience' that determines which agents are notified.

This enforces information asymmetry:
- Network agent sees: telemetry, forecasts, anomalies
- Policy agent sees: regulatory notices, policy conflicts
- Safety agent sees: emergency declarations, priority overrides
- Supervisor sees: everything (all events)
- 'all' audience: visible to everyone

Example usage:
    events = [
        Event(id="normal", slot=0, kind="state", audience=["all"], description="Normal operation"),
        Event(id="precursor", slot=15, kind="demand", audience=["network"], description="Demand rising"),
        Event(id="policy_conflict", slot=50, kind="policy", audience=["policy"], description="Border cap enforced"),
    ]
    feed = EventFeed(events)
    assert feed.visible("network", 50) == [events[0], events[1]]  # network doesn't see policy event
    assert feed.visible("policy", 50) == [events[0], events[1], events[2]]  # policy sees everything released by slot 50
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """A scenario event that occurs at a specific slot and is visible to certain agents."""
    
    id: str                              # Unique identifier within scenario
    slot: int                            # Time slot when event is released
    kind: str                            # "state", "demand", "forecast", "emergency", "policy", "fade", etc.
    audience: list[str]                  # Agents/roles that see this event; "all" visible to everyone
    description: str                     # Human-readable description
    payload: dict = field(default_factory=dict)  # Extra data (values, flags, etc.)
    
    def __repr__(self) -> str:
        return f"Event(id={self.id}, slot={self.slot}, kind={self.kind}, audience={self.audience})"


class EventFeed:
    """Manages event release and visibility based on agent/role and time."""
    
    def __init__(self, events: list[Event]):
        """Initialize with a list of events. Events should be sorted by slot."""
        self.events = sorted(events, key=lambda e: e.slot)
        self._released_so_far: dict[int, list[Event]] = {}  # Cached: slot -> events released by that slot
    
    def release(self, t: int) -> list[Event]:
        """Return events that should be released at exactly slot t (first-time release only)."""
        return [e for e in self.events if e.slot == t]
    
    def visible(self, agent: str, t: int) -> list[Event]:
        """Return all events visible to 'agent' by slot t (released by t and passing audience filter)."""
        visible_events = []
        for e in self.events:
            if e.slot > t:
                break  # Events are sorted; no more will be visible
            # Check if agent can see this event
            if "all" in e.audience or agent in e.audience:
                visible_events.append(e)
        return visible_events
    
    def __len__(self) -> int:
        return len(self.events)
    
    def __repr__(self) -> str:
        return f"EventFeed({len(self.events)} events, slots {self.events[0].slot}–{self.events[-1].slot})"
