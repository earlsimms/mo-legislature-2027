"""Short plain-English summaries for KEY bills only, written by xAI Grok.
Runs only when the XAI_API_KEY environment variable (a GitHub Actions secret) is present; otherwise it is skipped.
Source text is the official summary from the chamber (Senate summary on the bill page, House summary PDF).
Results are cached in site/data/summaries.json and only regenerated when the official summary changes."""
import hashlib
import re
import json
import os
import subprocess
import tempfile
from .http import get, session

API = "https://api.x.ai/v1/chat/completions"


def house_summary_text(url):
    try:
        pdf = get(url, binary=True)
    except Exception:
        return ""
    try:
        from .official_summaries import pdf_to_paragraphs
        return pdf_to_paragraphs(pdf)
    except Exception:
        return ""


def official_text(bill):
    if bill.get("official_summary"):
        return bill["official_summary"]
    if bill.get("summaries"):
        return house_summary_text(bill["summaries"][0]["url"])
    return ""


def grok(text, bill, model):
    key = os.environ.get("XAI_API_KEY")
    prompt = (f"Summarize Missouri {bill['bill_string'] or bill['id']} ({bill['title']}) in 2 to 3 short plain-English sentences "
              f"for a government-affairs professional. Say what it changes and who it affects. Use only the official summary below; "
              f"do not add facts.\n\nOFFICIAL SUMMARY:\n{text[:6000]}")
    r = session().post(API, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}),
                       timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def run(key_bills, path, cfg, log):
    try:
        cache = json.load(open(path))
    except Exception:
        cache = {}
    have_key = bool(os.environ.get("XAI_API_KEY"))
    made = 0
    for b in key_bills[: cfg.get("max_bills", 60)]:
        text = official_text(b)
        if not text.strip():
            continue
        h = hashlib.sha1(text.encode()).hexdigest()[:12]
        c = cache.get(b["id"])
        if c and c.get("hash") == h:
            b["ai_summary"] = c["summary"]
            continue
        if not have_key or not cfg.get("enabled", True):
            continue
        try:
            s = grok(text, b, cfg.get("model", "grok-4"))
            cache[b["id"]] = {"hash": h, "summary": s, "model": cfg.get("model", "grok-4")}
            b["ai_summary"] = s
            made += 1
        except Exception as e:
            log("grok_summaries", False, f"{b['id']}: {e}")
            break
    json.dump(cache, open(path, "w"), indent=1)
    log("grok_summaries", True, f"{made} new summaries" if have_key else "skipped: XAI_API_KEY not set (official summary excerpts shown instead)")
