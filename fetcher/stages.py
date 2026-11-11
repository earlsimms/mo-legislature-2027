"""Turn an official action history into a progress stage, current committee and outcome.
Works on both House XML wording ("Third Read and Passed (H)") and Senate wording ("S Third Read and Passed")."""
import re

STAGES = ["Filed", "{o} committee", "Perfected", "Passed {o}", "{s} committee", "Passed {s}", "Truly agreed & finally passed", "Signed or vetoed"]


def _side(text, chamber_bill):
    """Which chamber an action happened in: 'H', 'S', 'G' or ''."""
    m = re.search(r"\(([HSG])\)\s*$", text)
    if m:
        return m.group(1)
    m = re.match(r"^(S|H)\s", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(S|H)\s+(Third Read|Second Read|First Read|Informal|Formal|Calendar|adopted|refuses|concurs)", text)
    if m:
        return m.group(1)
    if re.search(r"Referred\s+(S|H)\s", text):
        return re.search(r"Referred\s+(S|H)\s", text).group(1)
    return ""


def committee_name(text):
    for pat in (r"Referred:\s*(.+?)\s*\([HS]\)", r"(?:Second [Rr]ead and [Rr]eferred|Re-referred|Referred)\s*:?\s*[SH]?\s+(.+?)(?:\s+Committee)?\s*$",
                r"Second read and referred:\s*(.+?)\s*\(S\)"):
        m = re.search(pat, text)
        if m:
            return re.sub(r"\s*\((?:H|S)\)$", "", m.group(1)).strip()
    return ""


REPORTED = re.compile(r"Reported Do Pass|Reported from|Reported Truly Perfected|Reported Duly Enrolled|Voted Do Pass|Reported Do Not Pass|Motion to Do Pass Failed|Voted Do Not Pass")


def analyze(bill):
    o = "H" if bill["chamber"] == "House" else "S"
    s = "S" if o == "H" else "H"
    stage = 1 if bill["actions"] else 0
    committee = ""
    committee_side = ""
    main = ("", "")
    in_committee = False
    outcome = ""
    floor = []  # floor-action dates by chamber, for audio/video archive links
    for a in bill["actions"]:
        t = a["text"]
        side = _side(t, bill["chamber"])
        if re.search(r"[Rr]eferred|Re-referred|Committed to", t) and not re.search(r"Fiscal (Review|Oversight)|Rules - (Legislative|Administrative)|Rules, Joint Rules", t):
            nm = committee_name(t)
            if nm:
                committee, committee_side, in_committee = nm, side or o, True
                main = (nm, side or o)
                if (side or o) == o:
                    stage = max(stage, 2)
                else:
                    stage = max(stage, 5)
        elif re.search(r"[Rr]eferred|Re-referred", t):
            nm = committee_name(t)
            if nm:  # fiscal/rules committees: track as current committee without changing the main stage
                committee, committee_side, in_committee = nm, side or o, True
        if REPORTED.search(t):
            in_committee = False
        if re.search(r"^Perfected|Reported Truly Perfected|Re-Perfected|Perfected by Consent", t) and (side or o) == o:
            stage = max(stage, 3)
        if re.search(r"Third Read and Passed", t):
            if (side or o) == o:
                stage = max(stage, 4)
            else:
                stage = max(stage, 6)
        if re.search(r"Third Read and Defeated", t):
            outcome = outcome or "Defeated"
        if re.search(r"Truly Agreed To and Finally Passed", t, re.I):
            stage = max(stage, 7)
        if re.search(r"Approved by Governor|Signed by Governor|Letter of approval from the Governor", t):
            stage, outcome = 8, "Signed"
        if re.search(r"Vetoed in Part", t):
            stage, outcome = 8, "Signed, vetoed in part"
        elif re.search(r"Vetoed by Governor|^Vetoed", t):
            stage, outcome = 8, "Vetoed"
        if re.search(r"Delivered to Secretary of State", t) and stage >= 7 and not outcome:
            outcome = "Delivered to Secretary of State"
        if re.search(r"^Withdrawn", t):
            outcome = "Withdrawn"
        if re.search(r"Third Read|Perfect|Taken Up|Informal Calendar|Formal Calendar|Adopt|Concur|Truly Agreed|Conference", t) and side in ("H", "S"):
            floor.append({"date": a["date"], "chamber": side})
    if not in_committee and main[0]:
        committee, committee_side = main
    labels = [x.format(o="House" if o == "H" else "Senate", s="Senate" if o == "H" else "House") for x in STAGES]
    if bill["type"].endswith("JR"):
        labels[7] = "Ballot (no Governor signature)"
    status = labels[stage - 1] if stage else "Filed"
    if stage == 8:
        status = outcome or "Governor acted"
    elif stage in (2, 5) and not in_committee and committee:
        status = f"Reported from {labels[stage - 1].replace(' committee', '')} committee"
    elif stage == 7 and bill["type"].endswith("JR"):
        status = "Truly agreed & finally passed (goes to ballot)"
    if outcome in ("Withdrawn", "Defeated"):
        status = outcome
    return {"stage": stage, "stage_labels": labels, "status": status, "outcome": outcome,
            "committee": committee, "committee_chamber": {"H": "House", "S": "Senate"}.get(committee_side, ""),
            "in_committee": in_committee, "floor_dates": floor}
