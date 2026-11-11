"""Official live video/audio links. Every URL here was checked to exist on November 11, 2026:
- House: house.mo.gov/HearingRoomFeeds.aspx lists the Sliq "Harmony" live feeds (video) for the chamber and
  hearing rooms 1, 3, 5, 6, 7 and the Joint Committee hearing room. House Hearing Room 4 has no listed feed.
- House archive video: house.mo.gov/MediaCenter.aspx -> "Archive Video" (Sliq recordings index).
- Senate: chamber.senate.mo.gov lists live AUDIO for the chamber, the Senate Lounge, and Senate Committee Rooms 1 and 2.
  The Senate does not livestream video. Senate floor audio archive (one mp3 per session day) is at
  senate.mo.gov/Media/AudioArchive/. The Senate has no committee-hearing archive."""
import re
from datetime import datetime
from bs4 import BeautifulSoup
from .http import get

SLIQ = "https://sg001-harmony.sliq.net/00325/harmony/en/powerbrowser/RoomRouter?location={}&viewMode=3"
STREAMS = {
    "house_chamber_video": {"label": "Watch House floor (live video)", "kind": "video", "url": SLIQ.format("Chamber%20Live")},
    "house_chamber_audio": {"label": "Listen to House floor (audio only)", "kind": "audio",
                            "url": "https://sg001-harmony.sliq.net/00325/harmony/en/PowerBrowser/RoomRouter?location=chamber&viewMode=3&globalStreamId=1"},
    "HR1": {"label": "Watch House Hearing Room 1", "kind": "video", "url": SLIQ.format("HR1%20Live")},
    "HR3": {"label": "Watch House Hearing Room 3", "kind": "video", "url": SLIQ.format("HR3%20Live")},
    "HR5": {"label": "Watch House Hearing Room 5", "kind": "video", "url": SLIQ.format("HR5%20Live")},
    "HR6": {"label": "Watch House Hearing Room 6", "kind": "video", "url": SLIQ.format("HR6%20Live")},
    "HR7": {"label": "Watch House Hearing Room 7", "kind": "video", "url": SLIQ.format("HR7%20Live")},
    "JCR": {"label": "Watch Joint Committee Hearing Room", "kind": "video", "url": SLIQ.format("JCR")},
    "senate_chamber_audio": {"label": "Listen to Senate floor (live audio)", "kind": "audio", "url": "https://chamber.senate.mo.gov/chamber"},
    "senate_lounge": {"label": "Listen: Senate Lounge (live audio)", "kind": "audio", "url": "https://chamber.senate.mo.gov/lounge"},
    "SCR1": {"label": "Listen: Senate Committee Room 1 (live audio)", "kind": "audio", "url": "https://chamber.senate.mo.gov/scr1"},
    "SCR2": {"label": "Listen: Senate Committee Room 2 (live audio)", "kind": "audio", "url": "https://chamber.senate.mo.gov/scr2"},
}
ARCHIVES = {
    "house_video": {"label": "House archived video (floor and hearings)", "url": "https://sg001-harmony.sliq.net/00325/Harmony/en/View/EventListView/20200831/-1"},
    "house_media_center": {"label": "House Media Center", "url": "https://house.mo.gov/MediaCenter.aspx"},
    "senate_audio": {"label": "Senate floor audio archive", "url": "https://www.senate.mo.gov/Media/AudioArchive/"},
}


def stream_for_room(room):
    """Map a hearing location string to a verified stream key, or None (no stream for that room)."""
    r = (room or "").lower()
    m = re.search(r"house hearing room\s*(\d)", r) or re.search(r"\bhr\s*(\d)\b", r)
    if m:
        k = f"HR{m.group(1)}"
        return k if k in STREAMS else None
    if re.search(r"joint (committee|hearing) room|\b117\b|\bjcr\b", r):
        return "JCR"
    m = re.search(r"\bscr\s*(\d)\b|senate committee room\s*(\d)", r)
    if m:
        k = f"SCR{m.group(1) or m.group(2)}"
        return k if k in STREAMS else None
    if "senate lounge" in r:
        return "senate_lounge"
    if "house chamber" in r:
        return "house_chamber_video"
    if "senate chamber" in r:
        return "senate_chamber_audio"
    return None


def senate_audio_archive(log):
    """{ 'YYYY-MM-DD': [ {label,url}, ... ] } from the Senate's floor audio archive page."""
    try:
        s = get(ARCHIVES["senate_audio"]["url"])
    except Exception as e:
        log("senate_audio_archive", False, str(e)); return {}
    out = {}
    for a in BeautifulSoup(s, "lxml").find_all("a", href=True):
        h = a["href"]
        m = re.search(r"DebateArchive/(\d{4})/(?:\d{6}/)?(\d{2})(\d{2})(\d{2})", h)
        if not m or not h.lower().endswith(".mp3"):
            continue
        d = f"20{m.group(4)}-{m.group(2)}-{m.group(3)}"
        out.setdefault(d, []).append({"label": re.sub(r"\s+", " ", a.get_text(" ", strip=True)), "url": h.replace(" ", "%20")})
    log("senate_audio_archive", bool(out), f"{len(out)} session days with floor audio")
    return out
