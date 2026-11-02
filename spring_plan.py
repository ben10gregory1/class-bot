#!/usr/bin/env python3
# spring_plan.py - one-off Spring 2027 planning pull (all modalities, incl. in-person).
# Reuses discover.py's Banner session/fetch/meets/classify. Writes to discovery/spring/:
#   terms.json          - Banner term list (confirms the Spring term code)
#   all_sections.csv    - every section: crn, course, title, credits, part, mode, meets, prof, seats, attrs
#   targets_rmp.csv     - target-course + gen-ed-attribute sections with RMP data
# Read-only against Banner + RMP. Never registers.

import csv, json, os, re, sys, time
from discover import SSB, session, fetch_all, meets, classify, POT_LABEL
from enrich import lookup_rmp

OUT = "discovery/spring"
TARGET_COURSES = {
    ("ACCT", "203"), ("ACCT", "204"), ("ECON", "200"), ("ECON", "201"),
    ("MATH", "104"), ("MATH", "250"), ("LATN", "102"), ("LATN", "201"),
    ("LATN", "202"), ("DSCI", "232"), ("POLI", "101"), ("POLI", "150"),
}
ATTR_KEYS = ("Humanities", "History", "Founding", "Math", "Logic", "Foreign")


def find_term(s):
    r = s.get(f"{SSB}/classSearch/getTerms", params={"searchTerm": "", "offset": 1, "max": 20}, timeout=30)
    terms = r.json()
    json.dump(terms, open(f"{OUT}/terms.json", "w"), indent=2)
    for t in terms:
        if "Spring 2027" in t.get("description", ""):
            return t["code"]
    sys.exit(f"FATAL: no Spring 2027 term in {terms}")


def prof_name(sec):
    names = [f["displayName"] for f in (sec.get("faculty") or []) if f.get("displayName")]
    if not names:
        return ""
    return re.sub(r"^(.*?),\s*(.*)$", r"\2 \1", names[0].strip())


def main():
    os.makedirs(OUT, exist_ok=True)
    import requests
    s0 = requests.Session(); s0.headers.update({"User-Agent": "Mozilla/5.0"})
    term = find_term(s0)
    print(f"Spring 2027 term code: {term}")
    s = session(term)
    raw = fetch_all(s, term)
    print(f"{len(raw)} sections")

    rows = []
    for sec in raw:
        attrs = [a.get("description", "") for a in (sec.get("sectionAttributes") or [])]
        rows.append({
            "crn": sec.get("courseReferenceNumber"),
            "subj": sec.get("subject"), "num": sec.get("courseNumber"),
            "course": f'{sec.get("subject")} {sec.get("courseNumber")}-{sec.get("sequenceNumber")}',
            "title": sec.get("courseTitle"),
            "cr": sec.get("creditHourLow") or sec.get("creditHours"),
            "part": POT_LABEL.get(str(sec.get("partOfTerm")), sec.get("partOfTerm")),
            "mode": classify(sec),
            "meets": "; ".join(f"{d} {b}-{e}" for d, b, e in meets(sec)),
            "prof": prof_name(sec),
            "seats": sec.get("seatsAvailable"), "cap": sec.get("maximumEnrollment"),
            "attrs": " | ".join(attrs),
        })
    cols = list(rows[0].keys())
    with open(f"{OUT}/all_sections.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

    tgt = [r for r in rows if (r["subj"], r["num"]) in TARGET_COURSES
           or any(k in r["attrs"] for k in ATTR_KEYS)]
    cache = {}
    for r in tgt:
        n = r["prof"]
        if n and n not in cache:
            cache[n] = lookup_rmp(n)
            time.sleep(0.4)
        r.update(cache.get(n) or {"rmp_flag": "no_prof"})
    fields = cols + ["rmp_rating", "rmp_difficulty", "rmp_retake_pct", "rmp_count", "rmp_tags", "rmp_flag"]
    with open(f"{OUT}/targets_rmp.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(tgt)
    print(f"{len(tgt)} target sections, {len(cache)} profs looked up")


if __name__ == "__main__":
    main()
