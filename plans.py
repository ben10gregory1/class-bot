#!/usr/bin/env python3
# plans.py - Plan A/B/C fallback rule for a term's picks. Alert only: never registers.
# Usage: python plans.py             (live seats -> today's best schedule)
#        python plans.py --practice  (live seats + simulated fills, nothing is sent)
# Config: config.json "plans" (minCredits, registered[], blocked[], slots[], bench[])

import argparse, itertools, json

DAYS = (("monday", "M"), ("tuesday", "T"), ("wednesday", "W"), ("thursday", "R"),
        ("friday", "F"), ("saturday", "S"), ("sunday", "U"))
PLAN = "ABCDEFGHIJ"


def meeting_slots(sec):
    """(day, begin, end) per meeting. discover.meets() writes Tue and Thu both as T, too vague here."""
    out = set()
    for mf in sec.get("meetingsFaculty") or []:
        mt = mf.get("meetingTime") or {}
        if mt.get("beginTime"):
            out |= {(c, mt["beginTime"], mt.get("endTime")) for d, c in DAYS if mt.get(d)}
    return out


def overlaps(a, b):
    return any(x[0] == y[0] and x[1] < y[2] and y[1] < x[2] for x in a for y in b)


def clash(a, b):
    pa, pb = str(a.get("partOfTerm")), str(b.get("partOfTerm"))
    # Express I (2) and Express II (3) never run at the same time
    if pa != pb and "1" not in (pa, pb):
        return False
    return overlaps(meeting_slots(a), meeting_slots(b))


def blocked(sec, windows):
    return any(overlaps(meeting_slots(sec), {(d, w["start"], w["end"]) for d in w["days"]})
               for w in windows)


def has_seat(sec):
    # A seat with people on the waitlist is held for them, not grabbable
    return (sec.get("seatsAvailable") or 0) > 0 and not sec.get("waitCount")


def course_of(sec):
    return f'{sec.get("subject")} {sec.get("courseNumber")}'


def credits_of(sec):
    return float(sec.get("creditHourLow") or 0)


def targets(plans):
    """Watch-style targets so fetch_watched pulls every section the plans name."""
    out = []
    for item in plans["slots"] + plans.get("bench", []):
        subject, number = item["course"].split()
        out.append({"subject": subject, "courseNumber": number,
                    "crns": [r["crn"] for r in item["rungs"]]})
    return out


def resolve(plans, by_crn):
    """Best schedule: most credits, earlier slots kept first, closest to Plan A, most seats."""
    regd = [by_crn[c] for c in plans.get("registered", []) if c in by_crn]
    windows = plans.get("blocked", [])
    # A registered bench section is fixed: it counts toward credits and blocks clashes
    slot_courses = {slot["course"] for slot in plans["slots"]}
    fixed = [s for s in regd if course_of(s) not in slot_courses]
    options = []
    for slot in plans["slots"]:
        held = [s for s in regd if course_of(s) == slot["course"]]
        if held:
            options.append([(0, held[0], None)])
            continue
        opts = [(i, by_crn[r["crn"]], r) for i, r in enumerate(slot["rungs"])
                if r["crn"] in by_crn and has_seat(by_crn[r["crn"]])
                and not blocked(by_crn[r["crn"]], windows)]
        options.append(opts + [None])

    best, best_key = None, None
    for combo in itertools.product(*options):
        chosen = [c[1] for c in combo if c] + fixed
        if any(clash(a, b) for a, b in itertools.combinations(chosen, 2)):
            continue
        key = (-sum(credits_of(s) for s in chosen),
               tuple(0 if c else 1 for c in combo),
               sum(c[0] for c in combo if c),
               -sum(max(s.get("seatsAvailable") or 0, 0) for s in chosen))
        if best_key is None or key < best_key:
            best, best_key = combo, key

    picks = []
    for slot, c in zip(plans["slots"], best):
        picks.append({"course": slot["course"],
                      "plan": None if not c else "reg" if not c[2] else PLAN[c[0]],
                      "crn": c[1]["courseReferenceNumber"] if c else None,
                      "why": c[2]["why"] if c and c[2] else ""})
    for s in fixed:
        picks.append({"course": course_of(s), "plan": "reg",
                      "crn": s["courseReferenceNumber"], "why": ""})
    chosen = [c[1] for c in best if c] + fixed
    credits = sum(credits_of(s) for s in chosen)
    done = {course_of(s) for s in fixed}
    # Bench only to stay at the credit floor, it replaces a slot that ran out of options
    for item in plans.get("bench", []):
        if item["course"] in done:
            continue
        if credits >= plans.get("minCredits", 0):
            break
        for r in item["rungs"]:
            sec = by_crn.get(r["crn"])
            if sec and has_seat(sec) and not blocked(sec, windows) \
                    and not any(clash(sec, s) for s in chosen):
                picks.append({"course": item["course"], "plan": "bench", "crn": r["crn"],
                              "why": r["why"]})
                chosen.append(sec)
                credits += credits_of(sec)
                break
    return {"picks": picks, "credits": credits}


def describe(p, by_crn):
    if not p["crn"]:
        return f'{p["course"]}: no option left'
    sec = by_crn[p["crn"]]
    days = {}
    for d, b, e in sorted(meeting_slots(sec), key=lambda x: "MTWRFSU".index(x[0])):
        days.setdefault((b, e), []).append(d)
    when = ", ".join(f'{"".join(v)} {b}-{e}' for (b, e), v in days.items()) or "no set time"
    prof = ", ".join(f.get("displayName", "") for f in sec.get("faculty") or []) or "TBA"
    return (f'{p["course"]} [{p["plan"]}] CRN {p["crn"]}, {when}, {prof}, '
            f'{sec.get("seatsAvailable")} seats')


def check(plans, secs, st, send, watched=()):
    """Alert on a changed best schedule and on backups dropping to one seat.
    An alert that fails leaves state unchanged, so the next poll retries it."""
    by_crn = {s.get("courseReferenceNumber"): s for s in secs}
    result = resolve(plans, by_crn)
    mem = st.setdefault("_plan", {})
    old = mem.get("picks") or {s["course"]: s["rungs"][0]["crn"] for s in plans["slots"]}
    new = {p["course"]: p["crn"] for p in result["picks"]}
    if new == old:
        mem["picks"] = new
    else:
        moved = [p for p in result["picks"] if old.get(p["course"]) != p["crn"]]
        floor = plans.get("minCredits", 0)
        lines = [describe(p, by_crn) + (f'\nWhy: {p["why"]}' if p["why"] else "") for p in moved]
        lines += [f"{c}: off the schedule" for c in old if c not in new]
        lines.append(f'Schedule now {result["credits"]:g} cr'
                     + (f", UNDER the {floor} cr floor" if result["credits"] < floor else ""))
        names = ", ".join(p["course"] for p in moved) or "schedule"
        if send(f"PLAN CHANGE: {names}", "\n\n".join(lines), "urgent"):
            mem["picks"] = new

    seats = mem.setdefault("seats", {})
    regd = set(plans.get("registered", []))
    current = {p["crn"] for p in result["picks"]}
    for item in plans["slots"] + plans.get("bench", []):
        for i, r in enumerate(item["rungs"]):
            sec, crn = by_crn.get(r["crn"]), r["crn"]
            if not sec or crn in regd or crn in watched:
                continue
            n = sec.get("seatsAvailable")
            if n == 1 and seats.get(crn) != 1 and not sec.get("waitCount"):
                who = "your pick" if crn in current else "backup"
                info = {"course": item["course"], "crn": crn,
                        "plan": PLAN[i] if item in plans["slots"] else "bench"}
                if not send(f'LAST SEAT: {item["course"]} CRN {crn} ({who})',
                            describe(info, by_crn), "urgent" if crn in current else "default"):
                    continue
            seats[crn] = n
    return result


def practice(plans, secs):
    def rung(i, j):
        return plans["slots"][i]["rungs"][j]["crn"]

    # (name, simulated seat counts, config overrides)
    scenarios = [
        ("Live seats, nothing simulated", {}, {}),
        ("ACCT 203 Plan A fills", {rung(0, 0): 0}, {}),
        ("ACCT 203 Plan A down to one seat, in watch[]", {rung(0, 0): 1}, {}),
        ("MATH 104 Plan B down to one seat, backup only", {rung(1, 1): 1}, {}),
        ("MATH 104 A and B fill", {rung(1, 0): 0, rung(1, 1): 0}, {}),
        ("All three MATH 104 rungs fill", {rung(1, j): 0 for j in range(3)}, {}),
        ("Collision: MATH 104 A and LATN 102 A fill, their Plan Bs clash",
         {rung(1, 0): 0, rung(4, 0): 0}, {}),
        ("Schedule change: blocked MW 1700-1900",
         {}, {"blocked": [{"days": "MW", "start": "1700", "end": "1900"}]}),
        ("Registered in ACCT 203 A, then it fills", {rung(0, 0): 0}, {"registered": [rung(0, 0)]}),
    ]
    for name, over, plan_over in scenarios:
        print(f"\n=== {name}")
        sim = [{**s, "seatsAvailable": over[s["courseReferenceNumber"]]}
               if s.get("courseReferenceNumber") in over else s for s in secs]
        p = {**plans, **plan_over}
        sent = []
        check(p, sim, {}, lambda t, b, pr: sent.append(f"[{pr}] {t}") or True)
        result = resolve(p, {s.get("courseReferenceNumber"): s for s in sim})
        for pick in result["picks"]:
            print(" ", describe(pick, {s.get("courseReferenceNumber"): s for s in sim}))
        print(f'  {result["credits"]:g} cr')
        print("  Phone:", " | ".join(sent) or "no alert from the plan rule")


def main():
    from discover import session
    from watch import fetch_watched
    p = argparse.ArgumentParser()
    p.add_argument("--practice", action="store_true")
    a = p.parse_args()
    cfg = json.load(open("config.json"))
    plans = cfg["plans"]
    secs = fetch_watched(session(cfg["term"]), cfg["term"], targets(plans))
    if a.practice:
        practice(plans, secs)
        return
    by_crn = {s.get("courseReferenceNumber"): s for s in secs}
    result = resolve(plans, by_crn)
    for pick in result["picks"]:
        print(describe(pick, by_crn))
    print(f'{result["credits"]:g} cr')


if __name__ == "__main__":
    main()
