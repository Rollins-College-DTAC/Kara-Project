"""Tests for dashboard/applications.py: deterministic SAMPLE application data."""

from datetime import date

from dashboard.applications import (RELEVANT, STATUSES, deadline_urgency, sample_application,
                                    upcoming_deadlines)

TODAY = date(2026, 11, 10)


def test_sample_application_is_deterministic_for_a_school_and_day():
    a = sample_application("LS-01", 50000, TODAY)
    b = sample_application("LS-01", 50000, TODAY)
    assert a == b


def test_every_status_is_valid_and_deadlines_are_in_the_future():
    for i in range(1, 31):
        app = sample_application(f"LS-{i:02d}", 50000, TODAY)
        assert app.status in STATUSES
        assert all(d.due > TODAY for d in app.deadlines)
        assert [d.label for d in app.deadlines] == sorted(
            [d.label for d in app.deadlines], key=lambda lbl: next(x.due for x in app.deadlines if x.label == lbl))


def test_deadlines_match_what_matters_at_that_status():
    for i in range(1, 31):
        app = sample_application(f"LS-{i:02d}", 50000, TODAY)
        assert {d.label for d in app.deadlines} == set(RELEVANT[app.status])


def test_only_accepted_or_waitlisted_applications_have_an_offer():
    for i in range(1, 31):
        app = sample_application(f"LS-{i:02d}", 50000, TODAY)
        has_offer = app.scholarship_offer is not None
        assert has_offer == (app.status in ("Accepted", "Waitlisted"))
        if has_offer:
            assert 0 < app.scholarship_offer < 50000


def test_all_four_statuses_appear_across_the_sample_schools():
    seen = {sample_application(f"LS-{i:02d}", 50000, TODAY).status for i in range(1, 31)}
    assert seen == set(STATUSES)


def test_upcoming_deadlines_are_sorted_and_skip_past_ones():
    apps = [sample_application(f"LS-{i:02d}", 50000, TODAY) for i in range(1, 8)]
    events = upcoming_deadlines(apps, TODAY)
    assert events == sorted(events)
    assert upcoming_deadlines(apps, date(2030, 1, 1)) == []


def test_deadline_urgency_thresholds():
    assert deadline_urgency(0) == "urgent" and deadline_urgency(14) == "urgent"
    assert deadline_urgency(15) == "soon" and deadline_urgency(30) == "soon"
    assert deadline_urgency(31) == "ok"
