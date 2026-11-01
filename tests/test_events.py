"""Test event engine with information asymmetry enforcement."""
from __future__ import annotations

import pytest

from scenarios.engine import Event, EventFeed


@pytest.fixture
def flood_relief_events():
    """Create a sample set of flood relief scenario events."""
    return [
        Event(id="start", slot=0, kind="state", audience=["all"], description="Start"),
        Event(id="precursor", slot=15, kind="demand", audience=["network"], description="Precursor"),
        Event(id="forecast", slot=25, kind="forecast", audience=["network", "supervisor"], description="Forecast"),
        Event(id="emergency", slot=28, kind="emergency", audience=["safety", "supervisor"], description="Emergency"),
        Event(id="fade", slot=45, kind="fade", audience=["all"], description="Fade"),
        Event(id="policy", slot=50, kind="policy", audience=["policy"], description="Policy"),
        Event(id="recovery", slot=61, kind="state", audience=["all"], description="Recovery"),
    ]


def test_event_creation():
    """Events should be created with required fields."""
    e = Event(
        id="test",
        slot=10,
        kind="state",
        audience=["network"],
        description="Test event",
    )
    assert e.id == "test"
    assert e.slot == 10
    assert e.kind == "state"
    assert "network" in e.audience
    assert e.payload == {}


def test_event_feed_initialization(flood_relief_events):
    """EventFeed should initialize and sort events."""
    feed = EventFeed(flood_relief_events)
    assert len(feed) == len(flood_relief_events)
    # Events should be sorted by slot
    for i in range(len(feed.events) - 1):
        assert feed.events[i].slot <= feed.events[i+1].slot


def test_release_returns_events_at_exact_slot(flood_relief_events):
    """release(t) should return only events at slot t (first-time release only)."""
    feed = EventFeed(flood_relief_events)
    
    # At slot 0, should get the start event
    released_0 = feed.release(0)
    assert len(released_0) == 1
    assert released_0[0].id == "start"
    
    # At slot 15, should get the precursor event
    released_15 = feed.release(15)
    assert len(released_15) == 1
    assert released_15[0].id == "precursor"
    
    # At slot 10 (no event), should get nothing
    released_10 = feed.release(10)
    assert len(released_10) == 0


def test_visible_enforces_audience_filter(flood_relief_events):
    """visible(agent, t) should return events agent can see at slot t."""
    feed = EventFeed(flood_relief_events)
    
    # At slot 50, network agent should NOT see the policy event
    visible_network = feed.visible("network", 50)
    visible_ids_network = [e.id for e in visible_network]
    assert "policy" not in visible_ids_network, "Network agent should not see policy event"
    
    # But policy agent should see it
    visible_policy = feed.visible("policy", 50)
    visible_ids_policy = [e.id for e in visible_policy]
    assert "policy" in visible_ids_policy, "Policy agent should see policy event"


def test_all_audience_is_visible_to_everyone(flood_relief_events):
    """Events with 'all' in audience should be visible to any agent."""
    feed = EventFeed(flood_relief_events)
    
    agents = ["network", "policy", "safety", "supervisor", "unknown"]
    for agent in agents:
        visible = feed.visible(agent, 61)  # After recovery event
        visible_ids = [e.id for e in visible]
        assert "recovery" in visible_ids, f"{agent} should see 'all' audience event"


def test_visible_includes_all_events_up_to_slot(flood_relief_events):
    """visible(agent, t) should include all events agent can see released by slot t."""
    feed = EventFeed(flood_relief_events)
    
    # Network should see all events up to slot 50 that have network in audience or 'all'
    visible = feed.visible("network", 50)
    visible_ids = {e.id for e in visible}
    
    # Network can see: start (all), precursor (network), forecast (network+supervisor), fade (all)
    # But NOT emergency (safety+supervisor), policy (policy)
    expected_visible_ids = {"start", "precursor", "forecast", "fade"}
    assert visible_ids == expected_visible_ids, f"Expected {expected_visible_ids}, got {visible_ids}"


def test_information_asymmetry_network_vs_policy(flood_relief_events):
    """Network and policy agents should have different visibility."""
    feed = EventFeed(flood_relief_events)
    
    visible_network = set(e.id for e in feed.visible("network", 50))
    visible_policy = set(e.id for e in feed.visible("policy", 50))
    
    # Network sees demand/forecast events but not policy
    assert "precursor" in visible_network
    assert "forecast" in visible_network
    assert "policy" not in visible_network
    
    # Policy sees policy events but not demand
    assert "policy" in visible_policy
    assert "precursor" not in visible_policy
    
    # Both see "all" audience events
    assert "start" in visible_network
    assert "start" in visible_policy
    assert "fade" in visible_network
    assert "fade" in visible_policy


def test_safety_agent_specific_visibility(flood_relief_events):
    """Safety agent should only see safety and 'all' events."""
    feed = EventFeed(flood_relief_events)
    
    visible = set(e.id for e in feed.visible("safety", 50))
    
    # Should see emergency (safety-specific) and 'all' events
    assert "emergency" in visible
    assert "start" in visible
    
    # Should NOT see network or policy specific events
    assert "precursor" not in visible
    assert "policy" not in visible


def test_supervisor_sees_many_events(flood_relief_events):
    """Supervisor should see events listed in its audience or with 'all'."""
    feed = EventFeed(flood_relief_events)
    
    visible_supervisor = set(e.id for e in feed.visible("supervisor", 100))
    
    # Supervisor is listed in audience for: forecast, emergency
    # Supervisor sees 'all' audience: start, fade, recovery
    # Supervisor does NOT see: precursor (network only), policy (policy only)
    expected = {"start", "forecast", "emergency", "fade", "recovery"}
    assert visible_supervisor == expected, f"Expected {expected}, got {visible_supervisor}"


def test_event_ordering_preserved(flood_relief_events):
    """Events should be released in slot order."""
    feed = EventFeed(flood_relief_events)
    
    # Manually walk through time and check ordering
    released_events = []
    for t in range(0, 100):
        released_events.extend(feed.release(t))
    
    # Released events should match original order (sorted by slot)
    for i in range(len(released_events) - 1):
        assert released_events[i].slot <= released_events[i+1].slot


def test_multiple_events_at_same_slot():
    """Multiple events can occur at the same slot."""
    events = [
        Event(id="e1", slot=10, kind="state", audience=["all"], description="Event 1"),
        Event(id="e2", slot=10, kind="state", audience=["all"], description="Event 2"),
        Event(id="e3", slot=10, kind="state", audience=["all"], description="Event 3"),
    ]
    feed = EventFeed(events)
    
    released = feed.release(10)
    assert len(released) == 3, "Should get all 3 events at slot 10"
    released_ids = set(e.id for e in released)
    assert released_ids == {"e1", "e2", "e3"}


def test_event_payload_carried_through(flood_relief_events):
    """Event payloads should be preserved."""
    events = [
        Event(
            id="data",
            slot=20,
            kind="state",
            audience=["all"],
            description="Event with payload",
            payload={"key": "value", "number": 42},
        ),
    ]
    feed = EventFeed(events)
    
    visible = feed.visible("any_agent", 20)
    assert len(visible) == 1
    assert visible[0].payload == {"key": "value", "number": 42}
