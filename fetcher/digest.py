"""Daily digest of KEY-bill changes. Writes site/data/digest.html and site/data/digest.md. Sends nothing."""
import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")


def fdate(iso):
    if not iso:
        return ""
    d = datetime.fromisoformat(iso[:10])
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def build(data, out_html, out_md, hours=24):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    key = [b for b in data["bills"] if b.get("key")]
    changed = [b for b in key if b.get("changed_at") and datetime.fromisoformat(b["changed_at"]) >= since]
    today = now.astimezone(CT).date()
    upcoming = []
    for h in data["hearings"]:
        if h.get("date") and today.isoformat() <= h["date"] <= (today + timedelta(days=7)).isoformat():
            ids = [x["id"] for x in h["bills"]]
            ks = [b for b in key if b["id"] in ids]
            if ks:
                upcoming.append((h, ks))
    nowct = now.astimezone(CT)
    stamp = f"{nowct.strftime('%B')} {nowct.day}, {nowct.year} at {nowct.strftime('%I:%M %p').lstrip('0')} CT"
    md = [f"# Key bill digest — {stamp}", "", f"{data['config']['session_label']}. {len(key)} key bills tracked.", ""]
    md.append(f"## Changed in the last {hours} hours ({len(changed)})")
    for b in changed or []:
        md.append(f"- **{b['label']}** — {b.get('short_title') or b['title']}: {b['status']}. Last action {fdate(b.get('last_action',{}).get('date',''))}: {b.get('last_action',{}).get('text','')} ([official page]({b['url']}))")
    if not changed:
        md.append("- No changes on key bills.")
    md += ["", "## Key bills with hearings in the next 7 days"]
    for h, ks in upcoming:
        md.append(f"- {fdate(h['date'])} {h['time']}, {h['chamber']} {h['committee']} ({h['room']}): " + ", ".join(b["label"] for b in ks))
    if not upcoming:
        md.append("- None scheduled.")
    open(out_md, "w").write("\n".join(md) + "\n")

    e = html.escape
    rows = "".join(
        f"<tr><td><a href='{e(b['url'])}'>{e(b['label'])}</a></td><td>{e(b.get('short_title') or b['title'])}</td><td>{e(b['status'])}</td>"
        f"<td>{e(fdate(b.get('last_action',{}).get('date','')))}: {e(b.get('last_action',{}).get('text',''))}</td></tr>" for b in changed) or "<tr><td colspan=4>No changes on key bills.</td></tr>"
    hrs = "".join(f"<li>{e(fdate(h['date']))} {e(h['time'])} — {e(h['chamber'])} {e(h['committee'])} ({e(h['room'])}): "
                  + ", ".join(e(b["label"]) for b in ks) + "</li>" for h, ks in upcoming) or "<li>None scheduled.</li>"
    doc = f"""<!doctype html><html><body style="font:14px Arial,sans-serif;color:#111;max-width:760px">
<div style="background:#0b3d6b;border-bottom:4px solid #a51c36;color:#fff;padding:10px 14px"><div style="font:600 11px Georgia,serif;letter-spacing:3px">MISSOURI STRATEGIES</div><b style="font-size:17px">Key bill digest</b><div style="font-size:12px">{e(stamp)}</div></div>
<h3>Changed in the last {hours} hours ({len(changed)})</h3>
<table cellpadding=6 style="border-collapse:collapse;width:100%" border=1><tr style="background:#f3f4f6"><th>Bill</th><th>Title</th><th>Status</th><th>Last action</th></tr>{rows}</table>
<h3>Key bills with hearings in the next 7 days</h3><ul>{hrs}</ul>
<p style="font-size:12px;color:#555">Data from house.mo.gov and senate.mo.gov.</p></body></html>"""
    open(out_html, "w").write(doc)
    return len(changed)
