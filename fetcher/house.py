"""Missouri House official XML exports (documents.house.mo.gov/xml). Updated hourly by the House.
The House asks that scripts poll no more than once every half hour."""
import re
import xml.etree.ElementTree as ET
from .http import get, pmap

BASE = "https://documents.house.mo.gov/xml"


def code(year, session="R"):
    # 2026 regular -> 261 ; 2027 regular -> 271 ; extraordinary S1 -> 262 etc.
    n = 1 if session == "R" else int(re.sub(r"\D", "", session) or 1) + 1
    return f"{str(year)[2:]}{n}"


def _x(s):
    s = s.lstrip("\ufeff")
    if not s.lstrip().startswith("<ROOT"):
        raise RuntimeError("not XML (House error page)")
    # House XML sometimes has stray '&'
    s = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", s)
    return ET.fromstring(s)


def t(el, path, default=""):
    e = el.find(path)
    return (e.text or "").strip() if e is not None and e.text else default


def members(year, session, log):
    c = code(year, session)
    try:
        root = _x(get(f"{BASE}/{c}-MemberList.xml"))
    except Exception as e:
        log("house_members", False, str(e)); return {}
    links = [t(r, "RepresentativeXMLLink") for r in root.findall("RepresentativeXML")]

    def one(u):
        try:
            r = _x(get(u)).find(".//RepresentativeInfo")
            return {"district": str(int(t(r, "DistrictNum") or 0)), "first": t(r, "FirstName"),
                    "last": t(r, "LastName"), "party": t(r, "Party")}
        except Exception:
            return None
    out = {m["district"]: m for m in pmap(one, links) if m}
    log("house_members", bool(out), f"{len(out)} representatives")
    return out


def bill_list(year, session, types, log):
    c = code(year, session)
    root = _x(get(f"{BASE}/{c}-BillList.XML"))
    items = []
    for b in root.findall("BillXML"):
        bt = t(b, "BillType")
        if bt in types:
            items.append((bt, t(b, "BillNumber"), t(b, "BillXMLLink")))
    log("house_bill_list", True, f"{len(items)} bills of types {','.join(types)}")
    return items


def parse_bill(xml, year, session):
    root = _x(xml)
    bi = root.find("BillInformation")
    num = t(bi, "BillNumber")
    m = re.match(r"([A-Z]+)(\d+)", num)
    bt, bn = m.group(1), m.group(2)
    actions = []
    for a in bi.findall("Action"):
        actions.append({"date": t(a, "PubDate")[:10], "text": t(a, "Description"),
                        "journal": t(a, "JournalLink")})
    sponsors = [{"type": t(s, "SponsorType"), "name": t(s, "FullName"), "district": str(int(t(s, "District") or 0))}
                for s in bi.findall("Sponsor")]
    texts = [{"name": t(x, "DocumentName"), "url": t(x, "BillTextLink"), "sort": t(x, "BillVersionSort")}
             for x in bi.findall("BillText") if t(x, "BillTextLink")]
    sums = [{"name": t(x, "DocumentName"), "url": t(x, "SummaryTextLink")} for x in bi.findall("BillSummary")
            if t(x, "SummaryTextLink")]
    subjects = [t(s, "SubjectName") for s in bi.findall("SubjectIndex") if t(s, "SubjectName")]
    gov = t(bi, "GovernorLastAction/GovernorAction")
    return {
        "id": f"{bt}{bn}", "type": bt, "number": int(bn), "chamber": "House",
        "bill_string": t(bi, "CurrentBillString"),
        "short_title": t(bi, "Title/ShortTitle"), "title": t(bi, "Title/LongTitle"),
        "lr": t(bi, "CurrentLRNumber"), "effective": t(bi, "ProposedEffectiveDate"),
        "last_action_raw": t(bi, "LastAction"),
        "next_hearing_raw": t(bi, "NextHouseHearing"), "calendar_raw": t(bi, "Calendar"),
        "governor_action": gov, "actions": actions, "sponsors": sponsors, "texts": texts, "summaries": sums,
        "subjects": subjects,
        "url": f"https://house.mo.gov/Bill.aspx?bill={bt}{bn}&year={year}&code={session}",
    }


def bills(year, session, types, log, workers=6):
    items = bill_list(year, session, types, log)
    errs = []

    def one(it):
        bt, bn, link = it
        try:
            return parse_bill(get(link), year, session)
        except Exception as e:
            errs.append(f"{bt}{bn}: {e}")
            return None
    out = [b for b in pmap(one, items, workers) if b]
    log("house_bills", bool(out), f"{len(out)} parsed, {len(errs)} failed" + (f" (e.g. {errs[0]})" if errs else ""))
    return out
