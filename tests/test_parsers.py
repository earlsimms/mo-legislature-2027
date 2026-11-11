"""Offline tests: hearing parsers against archived copies of the official schedule pages (Wayback Machine, March 2025),
plus stage logic. Run: python3 -m pytest -q tests  (or python3 tests/test_parsers.py)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fetcher import hearings, media, stages

F = os.path.join(os.path.dirname(__file__), "fixtures")


def test_house_hearings():
    h = hearings.parse_house(open(os.path.join(F, "house_hearings_2025-03-09_wayback.html"), errors="ignore").read(), 2025)
    assert len(h) >= 10 and h[0]["date"] == "2025-03-10" and h[0]["room"] == "House Hearing Room 7"
    assert any(b["exec"] for b in h[0]["bills"]) and media.stream_for_room(h[0]["room"]) == "HR7"


def test_senate_hearings():
    s = hearings.parse_senate(open(os.path.join(F, "senate_hrings_2025-03-05_wayback.html"), errors="ignore").read(), 2025)
    assert len(s) >= 10 and s[0]["date"] == "2025-03-05" and "SB100" in [b["id"] for b in s[0]["bills"]]
    assert media.stream_for_room("SCR 1 - 1st Floor") == "SCR1" and media.stream_for_room("House Hearing Room 4") is None


def test_stages():
    b = {"chamber": "House", "type": "HB", "actions": [
        {"date": "2026-01-07", "text": "Read First Time (H)"}, {"date": "2026-01-08", "text": "Referred: Commerce(H)"},
        {"date": "2026-02-01", "text": "Reported Do Pass (H)"}, {"date": "2026-02-10", "text": "Perfected (H)"},
        {"date": "2026-02-11", "text": "Third Read and Passed (H)"},
        {"date": "2026-03-01", "text": "Second read and referred: Education(S)"},
        {"date": "2026-04-01", "text": "Third Read and Passed (S)"}, {"date": "2026-05-01", "text": "Truly Agreed To and Finally Passed"},
        {"date": "2026-07-01", "text": "Approved by Governor (G)"}]}
    r = stages.analyze(b)
    assert r["stage"] == 8 and r["status"] == "Signed"
    b["actions"] = b["actions"][:6]
    r = stages.analyze(b)
    assert r["stage"] == 5 and r["committee"] == "Education" and r["in_committee"]


if __name__ == "__main__":
    test_house_hearings(); test_senate_hearings(); test_stages(); print("all tests passed")
