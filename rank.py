#!/usr/bin/env python3
# rank.py - score discovery/enriched_candidates.csv against the degree-plan
# remaining reqs (humanities, social science, math/logic, foreign lang, finance
# core) plus RMP signal, seats, and modality. Writes discovery/ranked_candidates.md.
#
# Composite (rows with usable RMP data):
#   retake_pct/100 * 3.0  + rating/5 * 2.5  + (5-difficulty)/5 * 1.5
#   + req_value(+3) + seats_bonus(+1 >10 / +2 >25) + modality_bonus(+1)
# Note: literal max is ~13.0, not 10 - the five weighted terms alone sum past
# 10 (3+2.5+1.5=7 base, +3+2+1 bonuses=13). Not clamped; ranking is relative.

import argparse, csv, json, re, sys

POT_LABEL = {"1": "Full Term", "2": "Express I", "3": "Express II", "9": "9 (unlabeled)"}


def load_attrs(raw_path):
    try:
        raw = json.load(open(raw_path, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for s in raw:
        out[s.get("courseReferenceNumber")] = [a.get("description", "") for a in (s.get("sectionAttributes") or [])]
    return out


def parse_course(course):
    m = re.match(r"^\s*([A-Z]+)\s+(\d+)", course or "")
    if not m:
        return "", 0
    return m.group(1), int(m.group(2))


def req_hit(subj, num, title, attrs):
    if any("Humanities" in a for a in attrs):
        return "Humanities"
    if any(a.strip() == "Social Science" for a in attrs):
        return "Social Science"
    if subj == "MATH" or (subj == "PHIL" and "logic" in (title or "").lower()):
        return "Math/Logic"
    if subj == "LATN" and num >= 201:
        return "Foreign Lang"
    if subj in ("ACCT", "ECON", "FINC") and 100 <= num <= 299:
        return "Finance core"
    return None


def modality_bonus(mode, part):
    if mode == "ASYNC":
        return 1
    if part == "3" and mode == "INPERSON":
        return 1
    return 0


def seats_bonus(seats):
    try:
        seats = int(seats)
    except Exception:
        return 0
    if seats > 25:
        return 2
    if seats > 10:
        return 1
    return 0


def to_float(v):
    try:
        return float(v)
    except Exception:
        return None


def score_row(r, attrs_by_crn):
    subj, num = parse_course(r["course"])
    attrs = attrs_by_crn.get(r["crn"], [])
    req = req_hit(subj, num, r.get("title", ""), attrs)
    req_val = 3 if req else 0
    seats_val = seats_bonus(r.get("seats"))
    mod_val = modality_bonus(r.get("mode"), r.get("part"))
    bonus_total = req_val + seats_val + mod_val

    rating = to_float(r.get("rmp_rating"))
    difficulty = to_float(r.get("rmp_difficulty"))
    retake = to_float(r.get("rmp_retake_pct"))
    count = to_float(r.get("rmp_count")) or 0
    flag = r.get("rmp_flag") or "no_rmp"

    has_rmp = flag == "ok" and rating is not None and difficulty is not None and retake is not None

    avoid = has_rmp and retake == 0 and count > 20

    if not has_rmp:
        composite = bonus_total
        bucket = "unranked"
    else:
        rmp_part = (retake / 100.0) * 3.0 + (rating / 5.0) * 2.5 + ((5.0 - difficulty) / 5.0) * 1.5
        composite = rmp_part + bonus_total
        bucket = "avoid" if avoid else "ranked"

    return {
        **r,
        "req": req or "",
        "composite": round(composite, 2),
        "bucket": bucket,
        "flag": flag,
    }


def fmt_row(r):
    part_label = POT_LABEL.get(r.get("part"), r.get("part"))
    return (f"| {r['crn']} | {r['course']} | {r['title']} | {r['cr']} | {part_label} | {r['mode']} | "
            f"{r['seats']} | {r['prof']} | {r.get('rmp_rating','')} | {r.get('rmp_difficulty','')} | "
            f"{r.get('rmp_retake_pct','')} | {r.get('rmp_count','')} | {r.get('req','') or 'none'} | "
            f"{r['composite']} |")


HEADER = ("| CRN | Course | Title | Cr | Part | Modality | Seats | Instructor | Rating | Difficulty | "
          "Retake% | #Ratings | Req | Score |")
SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="infile", default="discovery/enriched_candidates.csv")
    p.add_argument("--raw", default="discovery/raw_sections.json")
    p.add_argument("--out", default="discovery/ranked_candidates.md")
    a = p.parse_args()

    attrs_by_crn = load_attrs(a.raw)
    rows = list(csv.DictReader(open(a.infile, newline="", encoding="utf-8")))
    scored = [score_row(r, attrs_by_crn) for r in rows]

    ranked = sorted([r for r in scored if r["bucket"] == "ranked"], key=lambda r: -r["composite"])
    avoid = sorted([r for r in scored if r["bucket"] == "avoid"], key=lambda r: -r["composite"])
    unranked = sorted([r for r in scored if r["bucket"] == "unranked"], key=lambda r: -r["composite"])

    top30 = ranked[:30]

    out = []
    out.append("# Ranked candidates — discovery/enriched_candidates.csv\n")
    out.append(f"{len(rows)} total sections scored. {len(ranked)} ranked (usable RMP data), "
               f"{len(avoid)} avoid-flagged, {len(unranked)} unranked (no RMP data).\n")
    out.append("Composite = retake%/100*3.0 + rating/5*2.5 + (5-difficulty)/5*1.5 + req(+3) + "
                "seats(+1 >10/+2 >25) + modality(+1 ASYNC or Express II in-person). "
                "Literal max ~13, not clamped to 10 - weights alone sum past it.\n")

    out.append(f"## Top {len(top30)} sections\n")
    out.append(HEADER)
    out.append(SEP)
    for r in top30:
        out.append(fmt_row(r))
    out.append("")

    out.append(f"## Avoid-flagged ({len(avoid)}) — 0% retake with >20 ratings\n")
    if not avoid:
        out.append("None.\n")
    else:
        out.append(HEADER)
        out.append(SEP)
        for r in avoid:
            out.append(fmt_row(r))
    out.append("")

    out.append(f"## Unranked ({len(unranked)}) — no usable RMP data\n")
    if not unranked:
        out.append("None.\n")
    else:
        out.append("| CRN | Course | Title | Cr | Part | Modality | Seats | Instructor | Req | Flag | Score |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in unranked:
            part_label = POT_LABEL.get(r.get("part"), r.get("part"))
            out.append(f"| {r['crn']} | {r['course']} | {r['title']} | {r['cr']} | {part_label} | {r['mode']} | "
                       f"{r['seats']} | {r['prof']} | {r.get('req','') or 'none'} | {r['flag']} | {r['composite']} |")

    open(a.out, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"ranked={len(ranked)} avoid={len(avoid)} unranked={len(unranked)} -> {a.out}")
    print("\nTOP 5:")
    for r in top30[:5]:
        print(f"  {r['composite']:5.2f}  {r['crn']}  {r['course']:14s}  {r['prof']:25s} req={r.get('req') or 'none'}")
    if avoid:
        print("\nAVOID:")
        for r in avoid:
            print(f"  {r['crn']}  {r['course']:14s}  {r['prof']:25s} retake={r['rmp_retake_pct']} n={r['rmp_count']}")


if __name__ == "__main__":
    main()
