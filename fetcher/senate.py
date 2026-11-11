"""Missouri Senate official bill tracking (senate.mo.gov/BillTracking). HTML pages, parsed with BeautifulSoup."""
import re
import html as H
from datetime import datetime
from bs4 import BeautifulSoup
from .http import get, pmap

BT = "https://www.senate.mo.gov/BillTracking"


def _txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def bill_list(year, session, types, log):
    s = get(f"{BT}/Bills/BillList?year={year}&session={session}")
    soup = BeautifulSoup(s, "lxml")
    out = []
    for c in soup.select("div.card"):
        a = c.select_one(".bill-number a")
        if not a:
            continue
        num = _txt(a)
        m = re.match(r"([A-Z]+)\s*(\d+)", num)
        if not m or m.group(1) not in types:
            continue
        bid = re.search(r"billid=(\d+)", a["href"], re.I).group(1)
        sp = c.select_one(".bill-sponsor-handler a[href*='Senators/Member'], .bill-sponsor-handler a[href*='PastSenators']")
        hd = c.select_one(".bill-sponsor-handler a[href*='house.mo.gov']")
        out.append({"type": m.group(1), "number": int(m.group(2)), "billid": bid,
                    "sponsor_last": _txt(sp), "sponsor_mid": (("past:" if "PastSenators" in sp["href"] else "") + re.search(r"id=(\d+)", sp["href"]).group(1)) if sp else "",
                    "handler": _txt(hd), "title": _txt(c.select_one(".bill-title"))})
    log("senate_bill_list", bool(out), f"{len(out)} bills of types {','.join(types)}")
    return out


def senator(mid):
    past = mid.startswith("past:")
    url = (f"https://www.senate.mo.gov/senators/PastSenators?id={mid[5:]}" if past
           else f"https://www.senate.mo.gov/Senators/Member?id={mid}")
    s = get(url)
    t = re.sub(r"\s+", " ", BeautifulSoup(s, "lxml").get_text(" "))
    if past:
        party = re.search(r"archived page\..{0,200}?\b(Republican|Democrat\w*|Independent)\b", t)
        dist = re.search(r"Senator [^-]{2,40} - District (\d+)", t)
    else:
        party = re.search(r"\bParty .{0,60}?\b(Republican|Democrat\w*|Independent|Libertarian)\b", t)
        dist = re.search(r"\bDistrict District (\d+)", t) or re.search(r"Senatorial District (\d+)", t)
    name = re.search(r"Senator ([A-Z][\w.'\- ]+?) Party", t)
    return {"party": party.group(1) if party else "", "district": dist.group(1) if dist else "",
            "name": name.group(1) if name else ""}


def senators(mids, log):
    out = {}
    def one(m):
        try:
            return m, senator(m)
        except Exception:
            return m, None
    for m, v in pmap(one, sorted(set(x for x in mids if x)), 4):
        if v:
            out[m] = v
    log("senate_members", bool(out), f"{len(out)} senators (party/district from member pages)")
    return out


def info(year, billid):
    s = get(f"{BT}/Bills/BillInformation?year={year}&billid={billid}")
    soup = BeautifulSoup(s, "lxml")
    d = {}
    for it in soup.select(".detail-grid__item"):
        lab = _txt(it.select_one(".detail-grid__label"))
        val = _txt(it.select_one(".detail-grid__value"))
        if lab:
            d[lab] = val
    summ = ""
    t = re.sub(r"\s+", " ", soup.get_text(" "))
    m = re.search(r"CURRENT BILL SUMMARY (.+?)(?: [A-Z][A-Z .'\-]{3,40} ✕ Close| ✕ Close|$)", t)
    if m:
        summ = m.group(1).strip()
    return {"sponsor_full": d.get("Sponsor", ""), "lr": d.get("LR Number", ""), "bill_string": d.get("Title", ""),
            "handler_full": d.get("House Handler", ""), "journal": d.get("Journal Page", ""),
            "effective": d.get("Effective Date", ""), "committee": d.get("Committee", ""),
            "status": d.get("Current Status", ""), "official_summary": summ[:4000]}


def actions(year, billid, bt, bn):
    s = get(f"{BT}/Bills/BillList?billId={billid}&year={year}&billPrefix={bt}&billSuffix={bn}&handler=Actions")
    soup = BeautifulSoup(s, "lxml")
    out = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        ds = _txt(tds[0])
        try:
            iso = datetime.strptime(ds, "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        j = tds[2].find("a") if len(tds) > 2 else None
        out.append({"date": iso, "text": _txt(tds[1]), "journal": j["href"] if j else ""})
    out.reverse()  # page lists newest first; keep chronological like the House XML
    return out


def texts(year, billid):
    s = get(f"{BT}/Bills/BillList?billId={billid}&year={year}&handler=BillText")
    soup = BeautifulSoup(s, "lxml")
    out = []
    for i, a in enumerate(soup.select("a.link-card-item[href]")):
        nm = _txt(a)
        nm = re.sub(r"^\S+\s+-\s+", "", nm)  # drop LR number prefix
        out.append({"name": nm, "url": a["href"], "sort": str(i + 1)})
    return out


def summary(year, billid, bt, bn):
    """Most current official Senate summary: first card of the bill's Summaries panel. Text kept as published
    (paragraph breaks preserved, leading tab indents removed)."""
    s = get(f"{BT}/Bills/BillList?billId={billid}&year={year}&billPrefix={bt}&billSuffix={bn}&handler=Summaries")
    soup = BeautifulSoup(s, "lxml")
    card = soup.select_one(".summaries-list .card")
    if not card:
        return None
    body = card.select_one(".text-content--preformatted")
    if body is None:
        return None
    raw = body.get_text().replace("\r\n", "\n").replace("\r", "\n")
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n", raw)]
    text = "\n\n".join("\n".join(l.strip() for l in p.split("\n")) for p in paras if p)
    return {"version": _txt(card.select_one(".heading--label")), "text": text.strip()}


def bills(year, session, types, log, cache=None, workers=5):
    """cache: previous bills.json records keyed by id; actions/text re-fetched only when LR/status/journal changed
    or the cached copy is more than 12 hours old (keeps load on senate.mo.gov light)."""
    cache = cache or {}
    lst = bill_list(year, session, types, log)
    errs = []
    now = datetime.utcnow()

    def one(b):
        bid = f"{b['type']}{b['number']}"
        try:
            inf = info(year, b["billid"])
            old = cache.get(bid) or {}
            fresh = old.get("_src", {})
            sig = [inf["lr"], inf["status"], inf["journal"], inf["committee"]]
            age_ok = False
            if fresh.get("fetched"):
                try:
                    age_ok = (now - datetime.fromisoformat(fresh["fetched"])).total_seconds() < 12 * 3600
                except ValueError:
                    pass
            if old.get("actions") and fresh.get("sig") == sig and age_ok and "_summary" in old:
                acts, txs, fetched = old["actions"], old.get("texts", []), fresh["fetched"]
                summ = old["_summary"]
            else:
                acts = actions(year, b["billid"], b["type"], b["number"])
                summ = summary(year, b["billid"], b["type"], b["number"])
                txs = texts(year, b["billid"]) if (fresh.get("sig", [None])[0] != inf["lr"] or not old.get("texts")) else old["texts"]
                fetched = now.isoformat(timespec="seconds")
            return {
                "id": bid, "type": b["type"], "number": b["number"], "chamber": "Senate",
                "bill_string": inf["bill_string"] or f"{b['type']} {b['number']}",
                "short_title": "", "title": b["title"], "lr": inf["lr"], "effective": inf["effective"],
                "senate_committee": inf["committee"], "senate_status": inf["status"],
                "_summary": summ,
                "official_summary": (summ or {}).get("text") or inf["official_summary"],
                "official_summary_version": (summ or {}).get("version") or ("Current bill summary" if inf["official_summary"] else ""),
                "official_summary_url": f"{BT}/Bills/BillInformation?year={year}&billid={b['billid']}" if (summ or inf["official_summary"]) else "",
                "handler": inf["handler_full"] or b["handler"],
                "sponsor_last": b["sponsor_last"], "sponsor_full": inf["sponsor_full"], "sponsor_mid": b["sponsor_mid"],
                "actions": acts, "texts": txs, "subjects": [],
                "url": f"{BT}/Bills/BillInformation?year={year}&billid={b['billid']}",
                "_src": {"billid": b["billid"], "sig": sig, "fetched": fetched},
            }
        except Exception as e:
            errs.append(f"{bid}: {e}")
            return cache.get(bid)  # keep last good copy
    out = [x for x in pmap(one, lst, workers) if x]
    log("senate_bills", bool(out), f"{len(out)} parsed, {len(errs)} failed" + (f" (e.g. {errs[0]})" if errs else ""))
    return out, lst


def keywords(year, session, log):
    """Senate topical index -> {bill id: [topics]}"""
    try:
        s = get(f"{BT}/bills/keywords?year={year}&session={session}", timeout=90)
    except Exception as e:
        log("senate_topics", False, str(e)); return {}
    soup = BeautifulSoup(s, "lxml")
    out = {}
    for card in soup.select("div.card.collapsible"):
        kw = _txt(card.select_one(".heading--label"))
        for a in card.select("a.bill-number-color"):
            bid = _txt(a).replace(" ", "")
            out.setdefault(bid, [])
            if kw and kw not in out[bid]:
                out[bid].append(kw)
    log("senate_topics", bool(out), f"{len(out)} bills tagged")
    return out
