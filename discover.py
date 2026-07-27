#!/usr/bin/env python3
# discover.py - enumerate CofC Banner sections, filter to async / Express II, enrich w/ RMP.
# Usage: python discover.py --term 202710 --out candidates.csv
# Set BANNER env var to your working host (copy from existing bot).

import argparse, csv, json, os, re, sys, time
import requests

BASE = os.environ.get("BANNER", "https://bannerweb.cofc.edu")
SSB = f"{BASE}/StudentRegistrationSsb/ssb"
UA = {"User-Agent": "Mozilla/5.0"}
RMP_SCHOOL = "254"  # College of Charleston


def session(term):
    s = requests.Session()
    s.headers.update(UA)
    s.get(f"{SSB}/classSearch/classSearch", timeout=30)
    s.post(f"{SSB}/term/search?mode=search", data={"term": term}, timeout=30)
    return s


def vocab(s, term):
    """Dump filter code vocabularies. Codes vary by install - never hardcode."""
    out = {}
    for k in ("get_partOfTerm", "get_instructionalMethod", "get_subject"):
        try:
            r = s.get(f"{SSB}/classSearch/{k}",
                      params={"term": term, "offset": 1, "max": 200, "searchTerm": ""},
                      timeout=30)
            out[k] = r.json()
        except Exception as e:
            out[k] = f"ERR {e}"
    return out


def fetch_all(s, term, page=500):
    rows, off, total = [], 0, None
    while total is None or off < total:
        r = s.get(f"{SSB}/searchResults/searchResults",
                  params={"txt_term": term, "pageOffset": off,
                          "pageMaxSize": page, "sortColumn": "subjectDescription",
                          "sortDirection": "asc"}, timeout=60)
        d = r.json()
        total = d.get("totalCount", 0)
        chunk = d.get("data") or []
        if not chunk:
            break
        rows += chunk
        off += len(chunk)
        sys.stderr.write(f"\r{off}/{total}")
        time.sleep(0.3)
    sys.stderr.write("\n")
    return rows


def meets(sec):
    """Return list of (days, begin, end) for scheduled meetings."""
    out = []
    for mf in sec.get("meetingsFaculty") or []:
        mt = mf.get("meetingTime") or {}
        if mt.get("beginTime"):
            days = "".join(d[0].upper() for d in
                           ("monday", "tuesday", "wednesday", "thursday",
                            "friday", "saturday", "sunday") if mt.get(d))
            out.append((days, mt["beginTime"], mt.get("endTime")))
    return out


def classify(sec):
    m = meets(sec)
    im = (sec.get("instructionalMethodDescription") or "").lower()
    online = "online" in im or "distance" in im or "hybrid" in im
    if online and not m:
        return "ASYNC"
    if online and m:
        return "SYNC_ONLINE"
    return "INPERSON"


def rmp(name, cache={}):
    """Best-effort RMP lookup. Falls back to a manual search URL."""
    if not name or name in cache:
        return cache.get(name)
    url = f"https://www.ratemyprofessors.com/search/professors/{RMP_SCHOOL}?q={requests.utils.quote(name)}"
    res = {"rmp_rating": "", "rmp_diff": "", "rmp_again": "", "rmp_url": url}
    try:
        q = """query($t:String!,$s:ID!){newSearch{teachers(query:{text:$t,schoolID:$s}){
        edges{node{firstName lastName avgRating avgDifficulty wouldTakeAgainPercent numRatings legacyId}}}}}"""
        r = requests.post("https://www.ratemyprofessors.com/graphql",
                          json={"query": q, "variables": {"t": name, "s": "U2Nob29sLTI1NA=="}},
                          headers={**UA, "Authorization": "Basic dGVzdDp0ZXN0"}, timeout=20)
        e = r.json()["data"]["newSearch"]["teachers"]["edges"]
        if e:
            n = e[0]["node"]
            res.update(rmp_rating=n["avgRating"], rmp_diff=n["avgDifficulty"],
                       rmp_again=round(n["wouldTakeAgainPercent"] or -1),
                       rmp_url=f"https://www.ratemyprofessors.com/professor/{n['legacyId']}")
    except Exception:
        pass  # endpoint/auth drifts; manual URL still works
    cache[name] = res
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--term", default="202710")
    p.add_argument("--out", default="candidates.csv")
    p.add_argument("--no-rmp", action="store_true")
    p.add_argument("--dump-vocab", action="store_true")
    a = p.parse_args()

    s = session(a.term)
    if a.dump_vocab:
        print(json.dumps(vocab(s, a.term), indent=2))
        return

    raw = fetch_all(s, a.term)
    json.dump(raw, open("raw_sections.json", "w"))  # cache; re-filter offline

    keep = []
    for sec in raw:
        mode = classify(sec)
        if mode == "INPERSON":
            continue
        prof = ", ".join(f["displayName"] for f in (sec.get("faculty") or []) if f.get("displayName"))
        lead = prof.split(",")[0].strip()
        lead = re.sub(r"^(.*?),\s*(.*)$", r"\2 \1", lead)  # "Last, First" -> "First Last"
        row = {
            "crn": sec.get("courseReferenceNumber"),
            "course": f'{sec.get("subject")} {sec.get("courseNumber")}-{sec.get("sequenceNumber")}',
            "title": sec.get("courseTitle"),
            "cr": sec.get("creditHourLow") or sec.get("creditHours"),
            "part": sec.get("partOfTerm"),
            "mode": mode,
            "method": sec.get("instructionalMethodDescription"),
            "prof": lead,
            "seats": sec.get("seatsAvailable"),
            "cap": sec.get("maximumEnrollment"),
            "wait": sec.get("waitAvailable"),
            "meets": "; ".join(f"{d} {b}-{e}" for d, b, e in meets(sec)),
        }
        if not a.no_rmp and lead:
            row.update(rmp(lead))
        keep.append(row)

    keep.sort(key=lambda r: (r["mode"] != "ASYNC", -(float(r.get("rmp_rating") or 0)), r["course"]))
    cols = list(keep[0].keys()) if keep else []
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(keep)
    print(f"{len(keep)} sections -> {a.out}  (ASYNC: {sum(1 for r in keep if r['mode']=='ASYNC')})")


if __name__ == "__main__":
    main()
