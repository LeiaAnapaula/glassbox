from pathlib import Path

from snapcal.cua_demo import DemoRoute, prepare_pages
from snapcal.schema import EventCandidate


def test_handoff_contains_route_status_and_calendar_link(tmp_path: Path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"not-a-real-png")
    candidate = EventCandidate(
        kind="event", title="Demo event", start_local="2026-07-18T14:00"
    )
    page, _ = prepare_pages(tmp_path, image, DemoRoute("calendar", "Extracted.", event=candidate))
    text = page.read_text()
    assert "Screenshot Action Router" in text
    assert "CUA live status" in text
    assert "calendar.google.com/calendar/render" in text
    assert "Demo event" in text
    assert "human controls the consequential decision" in text


def test_glassbox_route_is_not_calendar(tmp_path: Path):
    from snapcal.triage_schema import ObservableStatement, TriageCandidate

    image = tmp_path / "shot.png"
    image.write_bytes(b"not-a-real-png")
    triage = TriageCandidate(
        kind="review", confidence=.8, summary="Review observable statements.",
        observable_statements=[ObservableStatement("request_for_help", "help me", "visible")],
        missing_context=["Identity and context are unknown"],
    )
    handoff, review = prepare_pages(
        tmp_path, image, DemoRoute("glassbox_review", "Human review.", triage=triage)
    )
    assert "Open Glassbox Review" in handoff.read_text()
    assert "calendar.google.com" not in handoff.read_text()
    assert "Not a trafficking determination" in review.read_text()
