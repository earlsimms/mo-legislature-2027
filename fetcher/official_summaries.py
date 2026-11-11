"""Official bill summaries, as published by each chamber (no rewriting).
House: the summary PDF for the bill's latest version (documents.house.mo.gov/billtracking/bills{code}/sumpdf/...), converted
       to text with pdftotext -layout, paragraphs kept. Cached by PDF URL in site/data/official_summaries_cache.json.
Senate: the first (most current) entry of the bill's "Summaries" panel on senate.mo.gov, fetched in senate.py."""
import json
import os
import re
import subprocess
import tempfile
from .http import get, pmap


def pdf_to_paragraphs(pdf_bytes):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes); f.flush()
        out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", f.name, "-"], capture_output=True, text=True, timeout=60).stdout
    return layout_to_paragraphs(out)


def layout_to_paragraphs(txt):
    paras, cur = [], []
    for line in txt.replace("\f", "\n").splitlines():
        s = line.strip()
        if not s:
            if cur:
                paras.append(cur); cur = []
            continue
        cur.append(s)
    if cur:
        paras.append(cur)
    out = []
    for p in paras:
        t = ""
        for s in p:
            if not t:
                t = s
            elif t.endswith("-") and not t.endswith(" -") and not t.endswith("--"):
                t += s          # line broke right after a hyphen in a hyphenated word ("court-" + "appointed")
            else:
                t += " " + s
        out.append(re.sub(r"[ \t]+", " ", t))
    return "\n\n".join(out).strip()


def house(bills, cache_path, log, workers=6):
    try:
        cache = json.load(open(cache_path))
    except Exception:
        cache = {}
    todo = []
    for b in bills:
        sums = b.get("summaries") or []
        if not sums:
            continue
        latest = sums[-1]  # House XML lists summary versions oldest -> newest
        b["official_summary_version"] = latest["name"]
        b["official_summary_url"] = latest["url"]
        if latest["url"] not in cache:
            todo.append(latest["url"])
    errs = []

    def one(u):
        try:
            return u, pdf_to_paragraphs(get(u, binary=True))
        except Exception as e:
            errs.append(f"{u}: {e}")
            return u, None
    for u, t in pmap(one, sorted(set(todo)), workers):
        if t:
            cache[u] = t
    n = 0
    for b in bills:
        u = b.get("official_summary_url")
        if u and cache.get(u):
            b["official_summary"] = cache[u]
            n += 1
    json.dump(cache, open(cache_path, "w"), separators=(",", ":"))
    log("house_summaries", n > 0, f"{n} bills with an official House summary ({len(todo)} PDFs downloaded this run, {len(errs)} failed)")
    return n
