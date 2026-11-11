"""Upcoming committee hearings from the official schedule pages.
House: house.mo.gov/HearingsTimeOrder.aspx   Senate: senate.mo.gov/HearingsSchedule/hrings.htm
Both pages only list current/future hearings (empty between sessions)."""
import re
from datetime import date, datetime
from bs4 import BeautifulSoup
from .http import get

HOUSE_URL = "https://house.mo.gov/HearingsTimeOrder.aspx"
SENATE_URL = "https://www.senate.mo.gov/HearingsSchedule/hrings.htm"
BILL_RE = re.compile(r"\b(HJR|HCR|HB|SJR|SCR|SB)\s*0*(\d+)\b")


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _date(s, year_hint):
    s = _clean(s).replace(".", "")
    s = re.sub(r"\s*-\s*(Upcoming|Adjourned|Cancelled|In Progress|Recess).*$", "", s, flags=re.I)
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y", "%A, %B %d", "%B %d", "%m/%d/%Y"):
        try:
            d = datetime.strptime(s, fmt)
            if "%Y" not in fmt:
                d = d.replace(year=year_hint)
            return d.date().isoformat()
        except ValueError:
            pass
    return ""


def parse_house(html, year_hint):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tbl in soup.find_all("table", id="cmtGroup"):
        rows = {}
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2 and tds[0].get_text(strip=True).endswith(":"):
                rows[tds[0].get_text(strip=True)[:-1].lower()] = _clean(tds[1].get_text(" "))
        if "committee" not in rows:
            continue
        h = {"chamber": "House", "committee": rows.get("committee", ""), "date": _date(rows.get("date", ""), year_hint),
             "date_raw": rows.get("date", ""), "time": rows.get("time", ""), "room": rows.get("location", ""),
             "note": rows.get("note", "")[:400], "status": "", "bills": [], "source": HOUSE_URL}
        st = re.search(r"-\s*(Upcoming|Adjourned|Cancelled|In Progress|Recess)", rows.get("date", ""), re.I)
        if st:
            h["status"] = st.group(1)
        # bill list table follows the header table
        nxt = tbl.find_next_sibling("table")
        if nxt is not None and nxt.get("id") == "cmtGroup" and "Committee:" not in nxt.get_text():
            exec_mode = False
            for el in nxt.find_all(["a", "i"]):
                if el.name == "i" and "Executive Session" in el.get_text():
                    exec_mode = True
                if el.name == "a" and "Bill.aspx" in (el.get("href") or ""):
                    m = BILL_RE.search(el.get_text(" "))
                    if m:
                        h["bills"].append({"id": f"{m.group(1)}{m.group(2)}", "exec": exec_mode})
        out.append(h)
    return out


def parse_senate(html, year_hint):
    soup = BeautifulSoup(html, "lxml")
    out = []
    cur = None
    for tbl in soup.find_all("table"):
        txt = _clean(tbl.get_text(" "))
        if txt.startswith("Committee:"):
            cur = {"chamber": "Senate", "committee": re.sub(r"^Committee:\s*", "", txt), "date": "", "date_raw": "",
                   "time": "", "room": "", "note": "", "status": "", "bills": [], "source": SENATE_URL}
            cur["committee"] = re.sub(r",\s*(Senator|Rep\.|Representative)\s.*$", "", cur["committee"])
            out.append(cur)
            continue
        if cur is None:
            continue
        m = re.search(r"Date:\s*(.+?)\s*Time:\s*(.+?)\s*Room:\s*(.+)$", txt)
        if m:
            cur["date_raw"], cur["time"], cur["room"] = m.group(1), m.group(2), m.group(3)
            cur["date"] = _date(m.group(1), year_hint)
            continue
        for a in tbl.find_all("a"):
            mm = BILL_RE.search(a.get_text(" "))
            if mm:
                bid = f"{mm.group(1)}{mm.group(2)}"
                if all(b["id"] != bid for b in cur["bills"]):
                    cur["bills"].append({"id": bid, "exec": False})
        if not tbl.find_all("a") and txt and not cur["note"]:
            cur["note"] = txt[:400]
    for h in out:
        if re.search(r"cancel", h["note"] + h["committee"], re.I):
            h["status"] = "Cancelled"
    return out


def fetch(year_hint, log):
    out = []
    for name, url, fn in (("house_hearings", HOUSE_URL, parse_house), ("senate_hearings", SENATE_URL, parse_senate)):
        try:
            hs = fn(get(url), year_hint)
            out += hs
            log(name, True, f"{len(hs)} hearings listed")
        except Exception as e:
            log(name, False, str(e))
    return out
