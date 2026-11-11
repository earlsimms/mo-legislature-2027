"""Build site/data/bills.json from the official Missouri House and Senate websites.

  python3 -m fetcher.fetch                # uses config.json
  python3 -m fetcher.fetch --previous-url https://earlsimms.github.io/mo-legislature-2027/data/full.json

Every step is tolerant: a failed source is logged in data.sources and the last good copy is kept."""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import house, senate, hearings, media, stages, summaries, digest, official_summaries
from .http import get

CT = ZoneInfo("America/Chicago")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "data")
SOURCES = []


ROUTINE = re.compile(r"^(Prefiled|Read First Time|Read Second Time|Introduced and Read First Time|S First Read|H First Read|H Second Read)|Referred|Re-referred", re.I)


def log(name, ok, detail):
    SOURCES.append({"name": name, "ok": bool(ok), "detail": detail,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(("OK  " if ok else "FAIL"), name, "-", detail, file=sys.stderr)


def party_abbr(p):
    p = (p or "").lower()
    return "R" if p.startswith("rep") else "D" if p.startswith("dem") else "I" if p.startswith("ind") else ""


def title_case(s):
    small = {"and", "of", "the", "for", "to", "in", "on", "or", "a"}
    w = s.lower().split()
    return " ".join(x if (i and x in small) else x.capitalize() for i, x in enumerate(w))


def last_action(acts):
    if not acts:
        return {"date": "", "text": ""}
    best = max(range(len(acts)), key=lambda i: (acts[i]["date"], i))
    a = acts[best]
    return {"date": a["date"], "text": re.sub(r"\s*\((H|S|G)\)\s*$", r" (\1)", a["text"])}


def last_hearing(acts):
    for a in reversed(acts):
        if re.search(r"Public Hearing Completed|Public Hearing Held|Hearing Conducted", a["text"]):
            return {"date": a["date"], "text": a["text"]}
    return None


def parse_next_house_hearing(raw):
    if not raw or raw.lower().startswith("hearing not scheduled"):
        return None
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", raw)
    d = datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat() if m else ""
    t = re.search(r"(\d{1,2}:\d{2}\s*[AP]M|Upon[^,]+)", raw, re.I)
    room = re.search(r"(House Hearing Room \d|Joint (?:Committee|Hearing) Room[^,]*|HR\s*\d|SCR\s*\d|Senate Lounge|House Chamber)", raw, re.I)
    return {"chamber": "House", "date": d, "time": t.group(1) if t else "", "room": room.group(1) if room else "",
            "committee": "", "raw": raw}


def tkey(t):
    m = re.search(r"(\d{1,2}):?(\d{2})?\s*([ap])\.?\s*m", t or "", re.I)
    if not m:
        return 9999
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0)
    return h * 60 + int(m.group(2) or 0)


def load_previous(path, url):
    try:
        if url:
            return json.loads(get(url))
        return json.load(open(path))
    except Exception:
        return None


def signature(b):
    return json.dumps([b["last_action"], b["status"], b["stage"], b.get("committee"),
                       [(h["date"], h["time"], h["committee"]) for h in b.get("hearings", [])], b.get("on_calendar")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--previous-url", default=os.environ.get("PREVIOUS_URL", ""))
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    year, sess = cfg["session_year"], cfg["session_code"]
    os.makedirs(DATA, exist_ok=True)
    prev = load_previous(os.path.join(DATA, "full.json"), args.previous_url)
    prev_bills = {b["id"]: b for b in (prev or {}).get("bills", [])}
    if prev and prev.get("config", {}).get("session_year") != year:
        prev_bills = {}  # new session: nothing to compare against

    now = datetime.now(timezone.utc)
    today_ct = now.astimezone(CT).date()

    # ---- House
    hb = []
    members = {}
    try:
        members = house.members(year, sess, log)
        hb = house.bills(year, sess, cfg["bill_types"]["House"], log, cfg["workers"]["house"])
    except Exception as e:
        log("house_bills", False, str(e))
    if not hb:
        hb = [b for b in prev_bills.values() if b["chamber"] == "House"]
    try:
        official_summaries.house(hb, os.path.join(DATA, "official_summaries_cache.json"), log, cfg["workers"]["house"])
    except Exception as e:
        log("house_summaries", False, str(e))
    # ---- Senate
    sb, sen = [], {}
    try:
        sb, lst = senate.bills(year, sess, cfg["bill_types"]["Senate"], log,
                               cache={k: v for k, v in prev_bills.items() if v["chamber"] == "Senate"},
                               workers=cfg["workers"]["senate"])
        sen = senate.senators([x["sponsor_mid"] for x in sb], log)
    except Exception as e:
        log("senate_bills", False, str(e))
    if not sb:
        sb = [b for b in prev_bills.values() if b["chamber"] == "Senate"]
    topics = senate.keywords(year, sess, log)
    hs = hearings.fetch(year if today_ct.year <= year else today_ct.year, log)
    hs = [h for h in hs if not h.get("date") or h["date"] >= today_ct.isoformat()]
    audio = media.senate_audio_archive(log)

    # ---- assemble
    by_hear = {}
    for h in hs:
        h["stream"] = media.stream_for_room(h["room"])
        for x in h["bills"]:
            by_hear.setdefault(x["id"], []).append(h)
    key_set = set(cfg.get("key_bills", []))
    out = []
    for b in hb + sb:
        b = dict(b)
        a = stages.analyze(b)
        b.update({k: v for k, v in a.items() if k != "floor_dates"})
        if b["chamber"] == "House":
            sp = next((s for s in b.get("sponsors", []) if s["type"] == "Sponsor"), (b.get("sponsors") or [{}])[0] if b.get("sponsors") else {})
            m = members.get(sp.get("district", ""), {})
            b["sponsor"] = {"name": sp.get("name", ""), "party": party_abbr(m.get("party")), "district": sp.get("district", ""), "chamber": "House"}
            b["cosponsors"] = len([s for s in b.get("sponsors", []) if s["type"] != "Sponsor"])
            b["topics"] = [title_case(s) for s in b.get("subjects", [])]
        else:
            nm = b.get("sponsor_full", "")
            nm = " ".join(reversed([p.strip() for p in nm.split(",", 1)])) if "," in nm else (nm or b.get("sponsor_last", ""))
            nm = re.sub(r"\s*\(\d+\)", "", nm)
            m = sen.get(b.get("sponsor_mid", ""), {})
            b["sponsor"] = {"name": nm, "party": party_abbr(m.get("party")), "district": m.get("district", ""), "chamber": "Senate"}
            b["topics"] = topics.get(b["id"], [])
            if b.get("senate_status") and not b["actions"]:
                b["status"] = b["senate_status"]
        b["label"] = f"{b['type']} {b['number']}"
        b["last_action"] = last_action(b["actions"])
        b["last_hearing"] = last_hearing(b["actions"])
        txs = sorted(b.get("texts", []), key=lambda x: int(x.get("sort") or 0), reverse=b["chamber"] == "House")
        b["text_url"] = txs[0]["url"] if txs else ""
        b["text_version"] = txs[0]["name"] if txs else ""
        # hearings: schedule pages + House per-bill "next hearing"
        hl = [{"chamber": h["chamber"], "committee": h["committee"], "date": h["date"], "time": h["time"],
               "room": h["room"], "status": h["status"], "stream": h["stream"]} for h in by_hear.get(b["id"], [])]
        nh = parse_next_house_hearing(b.get("next_hearing_raw", ""))
        if nh and not any(x["chamber"] == "House" for x in hl) and (not nh["date"] or nh["date"] >= today_ct.isoformat()):
            nh["stream"] = media.stream_for_room(nh["room"]); nh["committee"] = b.get("committee", ""); hl.append(nh)
        b["hearings"] = sorted(hl, key=lambda x: (x["date"] or "9999", tkey(x["time"])))
        cal = b.get("calendar_raw", "")
        cal = "" if (not cal or cal.startswith("Bill currently not")) else cal
        # the House keeps vetoed bills on a "VETOED HOUSE BILLS" calendar all year; it only matters in veto session (September)
        b["on_calendar"] = cal if (cal and ("VETO" not in cal.upper() or today_ct.month == 9)) else ""
        # floor recordings for the most recent floor days
        fd = []
        for f in reversed(a["floor_dates"]):
            if (f["date"], f["chamber"]) not in fd:
                fd.append((f["date"], f["chamber"]))
        rec = []
        for d, ch in fd[:6]:
            if ch == "S" and d in audio:
                for x in audio[d][:2]:
                    rec.append({"date": d, "chamber": "Senate", "kind": "audio", "label": "Senate floor audio", "url": x["url"]})
            if len(rec) >= 2:
                break
        if any(ch == "H" for _, ch in fd):
            rec.append({"date": next(d for d, ch in fd if ch == "H"), "chamber": "House", "kind": "video",
                        "label": "House archived video", "url": media.ARCHIVES["house_video"]["url"]})
        b["recordings"] = rec
        b["key"] = b["id"] in key_set
        # changed since the previous fetch
        old = prev_bills.get(b["id"])
        sig = signature(b)
        if old is None:
            b["changed_at"] = None if not prev_bills else now.isoformat(timespec="seconds")
            b["change"] = "" if not prev_bills else "New bill"
        elif old.get("_sig") != sig:
            b["changed_at"] = now.isoformat(timespec="seconds")
            b["change"] = "New action" if old.get("last_action") != b["last_action"] else ("New hearing" if old.get("hearings") != b["hearings"] else "Status changed")
        else:
            b["changed_at"], b["change"] = old.get("changed_at"), old.get("change", "")
        b["_sig"] = sig
        out.append(b)

    # ---- "moving this week" reference date
    ref = today_ct
    ref_note = ""
    if cfg.get("preview"):
        cnt = Counter(a["date"] for b in out for a in b["actions"]
                      if a["date"] and not re.search(r"Governor|Secretary of State|\(G\)", a["text"]))
        busy = sorted(d for d, n in cnt.items() if n >= 300)
        if busy:
            ref = datetime.fromisoformat(busy[-1]).date()
            ref_note = f"Preview: \"this week\" is measured back from {ref.strftime('%B')} {ref.day}, {ref.year}, the last day of the 2026 regular session."
    win = cfg.get("moving_window_days", 7)
    lo, hi = (ref - timedelta(days=win)).isoformat(), (today_ct + timedelta(days=win)).isoformat()
    for b in out:
        # routine paperwork (first/second reading, referrals) is not counted as "moving"
        recent = any(a["date"] and lo < a["date"] <= ref.isoformat() and not ROUTINE.search(a["text"]) for a in b["actions"])
        upcoming = any(h["date"] and h["date"] <= hi for h in b["hearings"]) or any(not h["date"] for h in b["hearings"])
        cal = bool(b["on_calendar"])
        b["moving"] = recent or upcoming or cal
        b["moving_why"] = "Upcoming hearing" if upcoming else "On House floor calendar" if cal else "Recent action" if recent else ""

    out.sort(key=lambda b: (["HB", "HJR", "SB", "SJR"].index(b["type"]) if b["type"] in ["HB", "HJR", "SB", "SJR"] else 9, b["number"]))
    key_bills = [b for b in out if b["key"]]
    if cfg.get("summaries", {}).get("enabled"):
        summaries.run(key_bills, os.path.join(DATA, "summaries.json"), cfg.get("summaries", {}), log)
    # official summaries: short preview in bills.json, full text in summaries-full.json (loaded only when a card is expanded)
    full_sums = {}
    for b in out:
        t = b.get("official_summary") or ""
        if not t:
            continue
        full_sums[b["id"]] = {"version": b.get("official_summary_version", ""), "url": b.get("official_summary_url", ""), "text": t}
        # card preview skips the House header lines (bill heading, SPONSOR:, COMMITTEE ACTION:); the full text keeps them
        paras = t.split("\n\n")
        if b["chamber"] == "House":
            while len(paras) > 1 and (" -- " in paras[0] or re.match(r"(SPONSOR|COMMITTEE ACTION|COMMITTEE OF ORIGIN)\b", paras[0])):
                paras = paras[1:]
        body = " ".join(" ".join(paras).split())
        b["sum_preview"] = body if len(body) <= 260 else body[:260].rsplit(" ", 1)[0] + "…"
        b["sum_full_len"] = len(t)
        b["sum_version"] = b.get("official_summary_version", "")
        b["sum_url"] = b.get("official_summary_url", "")
    json.dump(full_sums, open(os.path.join(DATA, "summaries-full.json"), "w"), separators=(",", ":"))

    data = {
        "generated": now.isoformat(timespec="seconds"),
        "config": {k: cfg[k] for k in ("session_year", "session_code", "title", "session_label", "preview", "preview_note", "key_bills") if k in cfg},
        "show_ai": bool(cfg.get("summaries", {}).get("enabled") and cfg.get("summaries", {}).get("show_on_cards")),
        "moving_reference": ref.isoformat(), "moving_note": ref_note,
        "streams": media.STREAMS, "archives": media.ARCHIVES,
        "hearings": sorted(hs, key=lambda h: (h["date"] or "9999", tkey(h["time"]))),
        "sources": SOURCES,
        "bills": out,
    }
    # full copy (cache for next run) and compact copy for the page
    json.dump(data, open(os.path.join(DATA, "full.json"), "w"), separators=(",", ":"))
    keep = ("id", "type", "number", "chamber", "label", "bill_string", "short_title", "title", "sponsor", "cosponsors", "topics",
            "stage", "status", "outcome", "committee", "committee_chamber", "in_committee", "last_action", "last_hearing",
            "hearings", "on_calendar", "recordings", "text_url", "text_version", "url", "key", "changed_at", "change",
            "moving", "moving_why", "effective", "handler", "sum_preview", "sum_full_len", "sum_version", "sum_url")
    if cfg.get("summaries", {}).get("enabled") and cfg.get("summaries", {}).get("show_on_cards"):
        keep = keep + ("ai_summary",)
    compact = dict(data)
    compact["bills"] = [{k: b[k] for k in keep if b.get(k) not in (None, "", [], False) or k in ("stage", "key")} for b in out]
    compact["stage_labels"] = {"House": stages.analyze({"chamber": "House", "type": "HB", "actions": []})["stage_labels"],
                               "Senate": stages.analyze({"chamber": "Senate", "type": "SB", "actions": []})["stage_labels"]}
    json.dump(compact, open(os.path.join(DATA, "bills.json"), "w"), separators=(",", ":"))
    n = digest.build(compact, os.path.join(DATA, "digest.html"), os.path.join(DATA, "digest.md"))
    print(f"wrote {len(out)} bills ({len(key_bills)} key, {sum(b['moving'] for b in out)} moving, "
          f"{len(hs)} upcoming hearings, {n} key bills changed in 24h)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
