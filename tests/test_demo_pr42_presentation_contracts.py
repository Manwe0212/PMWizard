"""PR #42 presentation regressions for read-only workspace navigation.

Source-level contracts complement the Docker UAT API checks and web build.
They do not replace browser click-through testing.
"""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def read(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def test_forecast_never_falls_back_to_planned_date():
    memory = read("components/memory-workspace.tsx")
    delivery = read("components/delivery-workspace.tsx")
    assert "forecast_end_date || project.planned_end_date" not in memory
    assert "Forecast: {project.forecast_end_date ?" in memory
    assert "Not recorded" in memory
    assert "project.planned_end_date && project.forecast_end_date" in delivery


def test_calendar_only_dates_are_formatted_using_utc():
    for component in ("components/memory-workspace.tsx", "components/delivery-workspace.tsx"):
        source = read(component)
        assert 'timeZone: "UTC"' in source
        assert 'T12:00:00Z' in source


def test_delivery_flags_have_contextual_memory_navigation():
    delivery = read("components/delivery-workspace.tsx")
    navigation = read("components/inbox-client.tsx")
    memory = read("components/memory-workspace.tsx")
    assert "sectionForFlag(flag.type)" in delivery
    assert "deliverySignalControls" in delivery
    assert "deliveryInspectButton" in delivery
    assert "setReturnToDelivery(true)" in navigation
    assert "onBackToDelivery={returnToDelivery ?" in navigation
    assert "← Back to Delivery Intelligence" in memory


def test_compact_delivery_card_layout_has_responsive_controls():
    css = read("app/globals.css")
    assert ".deliverySignalControls {display:flex" in css
    assert ".deliverySignalCopy {display:grid" in css
    assert ".deliveryInspectButton" in css
    assert ".memoryOverviewItem small" in css
