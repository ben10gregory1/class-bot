#!/usr/bin/env python3
# enrich.py - add RateMyProfessors data to discover.py's candidates.csv.
# Usage: python enrich.py [--in discovery/candidates.csv] [--out discovery/enriched_candidates.csv]
#        [--cache /tmp/rmp_cache.json] [--limit N]

import argparse, csv, json, os, sys, time
import requests

RMP_SCHOOL_ID = "U2Nob29sLTI1NA=="  # base64 "School-254" = College of Charleston
RMP_GRAPHQL = "https://www.ratemyprofessors.com/graphql"
UA = {"User-Agent": "Mozilla/5.0"}
AUTH = "Basic dGVzdDp0ZXN0"  # RMP's public test:test basic-auth token

SEARCH_QUERY = """query($t:String!,$s:ID!){newSearch{teachers(query:{text:$t,schoolID:$s}){
  edges{node{
    id firstName lastName avgRating avgDifficulty numRatings wouldTakeAgainPercent
  }}
}}}"""

# teacherRatingTags is not populated on the search result node - RMP only fills it
# on a direct node-by-id lookup. Empty tags for a real prof (0 tag submissions) is
# a legitimate outcome, not a failure - only missing/errored lookups get flagged.
TAGS_QUERY = """query($id:ID!){ node(id:$id) { ... on Teacher { teacherRatingTags { tagName tagCount } } } }"""

FIELDS = ["rmp_rating", "rmp_difficulty", "rmp_retake_pct", "rmp_count", "rmp_tags", "rmp_flag"]


def load_cache(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def save_cache(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    json.dump(cache, open(path, "w"), indent=2)


def empty_result(flag):
    return {"rmp_rating": None, "rmp_difficulty": None, "rmp_retake_pct": None,
            "rmp_count": None, "rmp_tags": None, "rmp_flag": flag}


def lookup_rmp(name, retries=2):
    """Query RMP's GraphQL search for a professor name at CofC. Never raises."""
    for attempt in range(retries):
        try:
            r = requests.post(RMP_GRAPHQL,
                               json={"query": SEARCH_QUERY, "variables": {"t": name, "s": RMP_SCHOOL_ID}},
                               headers={**UA, "Authorization": AUTH}, timeout=20)
            r.raise_for_status()
            body = r.json()
            if body.get("errors"):
                raise RuntimeError(body["errors"][0].get("message", "graphql error"))
            edges = body["data"]["newSearch"]["teachers"]["edges"]
            if not edges:
                return empty_result("no_rmp")
            n = edges[0]["node"]

            tags = []
            try:
                r2 = requests.post(RMP_GRAPHQL,
                                    json={"query": TAGS_QUERY, "variables": {"id": n["id"]}},
                                    headers={**UA, "Authorization": AUTH}, timeout=20)
                node2 = (r2.json().get("data") or {}).get("node") or {}
                tags = node2.get("teacherRatingTags") or []
            except Exception:
                pass  # tags are a bonus field - a failed second call shouldn't sink the whole lookup

            tags = sorted(tags, key=lambda t: -(t.get("tagCount") or 0))
            top_tags = "; ".join(t["tagName"] for t in tags[:5])
            count = n.get("numRatings") or 0
            res = {
                "rmp_rating": n.get("avgRating"),
                "rmp_difficulty": n.get("avgDifficulty"),
                "rmp_retake_pct": n.get("wouldTakeAgainPercent"),
                "rmp_count": count,
                "rmp_tags": top_tags,
                "rmp_flag": "low_data" if count < 5 else "ok",
            }
            return res
        except Exception as e:
            if attempt + 1 == retries:
                res = empty_result("api_error")
                res["rmp_flag"] = f"api_error: {e}"
                return res
            time.sleep(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="infile", default="discovery/candidates.csv")
    p.add_argument("--out", default="discovery/enriched_candidates.csv")
    p.add_argument("--cache", default="/tmp/rmp_cache.json")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    rows = list(csv.DictReader(open(a.infile, newline="", encoding="utf-8")))
    if a.limit:
        rows = rows[: a.limit]

    cache = load_cache(a.cache)
    names = sorted({r["prof"].strip() for r in rows if r.get("prof", "").strip()})

    for i, name in enumerate(names):
        if name in cache:
            continue
        print(f"  [{i+1}/{len(names)}] RMP lookup: {name}", file=sys.stderr)
        cache[name] = lookup_rmp(name)
        save_cache(a.cache, cache)  # persist after every lookup - survives a crash mid-run

    fieldnames = list(rows[0].keys()) + FIELDS if rows else []
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            name = r.get("prof", "").strip()
            enrich = cache.get(name) if name else empty_result("no_rmp")
            w.writerow({**r, **enrich})

    print(f"{len(rows)} rows -> {a.out} ({len(names)} unique instructors, "
          f"{sum(1 for v in cache.values() if v.get('rmp_flag')=='ok')} matched)")


if __name__ == "__main__":
    main()
