# Missouri General Assembly Bill Tracker (Missouri Strategies)

A card dashboard of every House and Senate bill and joint resolution, built like the election-night dashboard
(same cards, Missouri Strategies header, real dark mode, key-item stars). Live at https://earlsimms.github.io/mo-legislature-2027/ (repo earlsimms/mo-legislature-2027). Updates hourly January–May, daily in December.

## What's here
| Path | What it does |
|---|---|
| `config.json` | Session year/code, preview flag, default key bills, Grok model. **For 2027: set `session_year` to 2027, `session_label` to "2027 Regular Session", `preview` to false.** |
| `fetcher/` | Python fetcher. `python3 -m fetcher.fetch` writes `site/data/bills.json` (page), `full.json` (cache + "changed" baseline), `digest.html` / `digest.md`, `summaries.json`. |
| `site/template.html` → `build_page.py` → `site/index.html` | The page; `build_page.py` inlines the logo as a data URI. |
| `.github/workflows/update.yml` | Hourly January–May, daily in December, plus manual run. Prepared, not pushed. |
| `tests/` | Offline parser tests using archived (March 2025) copies of the official hearing pages. |

Run locally: `pip install beautifulsoup4 lxml curl_cffi pymupdf`, then
`python3 -m fetcher.fetch && python3 build_page.py && cd site && python3 -m http.server` → http://localhost:8000
(`?theme=dark`, `?tab=moving|cal|house|senate|jr` work in the URL).

## Data sources (all official, no API keys)
- **House:** `documents.house.mo.gov/xml/{YY}{n}-BillList.XML` + one XML per bill (actions, sponsor, subjects, bill text, summaries,
  next hearing, floor calendar) and the member XMLs (party). The House asks for no more than one pull every 30 minutes; we pull hourly.
- **Senate:** `senate.mo.gov/BillTracking/Bills/BillList`, each bill's BillInformation page, its Actions and Bill Text panels,
  the senator pages (party/district), and the Senate topical index (topics). Actions/text are re-downloaded only when a bill's
  status/LR number/journal page changes or every 12 hours.
- **Hearings:** `house.mo.gov/HearingsTimeOrder.aspx` and `senate.mo.gov/HearingsSchedule/hrings.htm` (empty between sessions).
- **Watch / listen (verified November 11, 2026):** House live video via Sliq for the chamber (plus audio-only), Hearing Rooms 1, 3, 5, 6, 7 and the
  Joint Committee Room (listed on `house.mo.gov/HearingRoomFeeds.aspx`; Hearing Room 4 has no feed). House archive video index.
  Senate live **audio only** at `chamber.senate.mo.gov/` (chamber, lounge, Committee Rooms 1 and 2) and the Senate floor audio archive
  (one mp3 per session day, linked on bill cards for the days the bill was on the Senate floor).

## Key bills
Default list in `config.json` → `key_bills`. Anyone can star/unstar on a card; that's saved in their browser (localStorage).

## Official bill summaries (every card)
Each card shows the chamber's own published summary for the bill's most current version, labeled with that version
(Introduced, Committee, Perfected, Senate Substitute, Truly Agreed and Finally Passed, …). Text is not rewritten.
- House: the latest summary PDF listed in the bill's XML (`documents.house.mo.gov/billtracking/bills{code}/sumpdf/…`), converted with
  PyMuPDF (falls back to `pdftotext -layout`), paragraphs kept. PDF text is cached by URL (`site/data/official_summaries_cache.json`), so only new versions download.
- Senate: the first (current) entry of the bill's Summaries panel on senate.mo.gov.
The card shows a short preview; "Read full summary" loads the complete text from `site/data/summaries-full.json` (loaded only on first
expand) and links to the official PDF / Senate bill page. `?open=HB1696` in the URL opens one bill's summary.
House appropriations bills (HB 2–20, HB 2002–2020 in 2026) have no House summary, so their cards say "No official summary posted yet."

## Grok summaries (optional, off)
`fetcher/summaries.py` can send the official summary of key bills to xAI Grok (`https://api.x.ai/v1/chat/completions`). It runs only if
`summaries.enabled` is true in config.json and the `XAI_API_KEY` repository secret exists; cards show it only if `show_on_cards` is also true.

## Daily digest
Each run writes `site/data/digest.html` (email-ready) and `digest.md`: key bills changed in the last 24 hours + key-bill hearings in the next
7 days. Nothing is sent. Delivery options to decide: (a) a once-a-day GitHub Actions step that emails `digest.html` through an SMTP/SendGrid
secret, or (b) a Grok Bot routine that reads the published `digest.html` each morning and emails it.

## Known limits
- Party is blank for a few House sponsors who are no longer in the House member list (for example, a member who left mid-term).
- "Changed today" compares with the previous fetch, so the first run after a reset shows no badges.
- House archive video can't be deep-linked to a specific day (the Sliq archive loads by script), so cards link to the archive index.
