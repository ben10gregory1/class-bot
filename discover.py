#!/usr/bin/env python3
"""
Discover real Banner codes and section data for a term, so you know what to
put in config.json before running watch.py.

  export BANNER=ssb.cofc.edu          # host from your existing bot (no scheme/path)
  python discover.py --dump-vocab     # vocab.json: subject / partOfTerm / campus / ... codes
  python discover.py --term 202710    # writes candidates.csv + raw_sections.json
  python discover.py --term 202710 --subject MATH --course 104   # narrow the search

vocab.json's "partOfTerm" list is what you need to sanity-check the term code
you're using actually has offerings; candidates.csv is a flat, spreadsheet-
friendly view of every section discover.py found, with the CRNs you'll copy
into config.json.
"""
import argparse
import csv
import json
import os
import sys

from banner import BannerClient

VOCAB_ENDPOINTS = ["subject", "partOfTerm", "campus", "instructionalMethod", "attribute"]

CSV_FIELDS = [
    "subject",
    "courseNumber",
    "sequenceNumber",
    "courseReferenceNumber",
    "courseTitle",
    "term",
    "partOfTerm",
    "partOfTermDescription",
    "campusDescription",
    "scheduleTypeDescription",
    "seatsAvailable",
    "maximumEnrollment",
    "enrollment",
    "instructor",
]


def flatten(section):
    faculty = section.get("faculty") or []
    instructor = ", ".join(f.get("displayName", "") for f in faculty if f.get("displayName"))
    row = {field: section.get(field) for field in CSV_FIELDS}
    row["instructor"] = instructor
    return row


def cmd_dump_vocab(client, term, out_dir):
    vocab = {"term": term}
    for name in VOCAB_ENDPOINTS:
        try:
            vocab[name] = client.get_vocab(name, term)
        except Exception as exc:
            vocab[name] = {"error": str(exc)}
    try:
        vocab["terms"] = client.get_terms()
    except Exception as exc:
        vocab["terms"] = {"error": str(exc)}

    path = os.path.join(out_dir, "vocab.json")
    with open(path, "w") as f:
        json.dump(vocab, f, indent=2)
    print(f"Wrote {path}")

    part_of_term = vocab.get("partOfTerm")
    if isinstance(part_of_term, list) and part_of_term:
        print("\npartOfTerm codes:")
        for row in part_of_term:
            print(f"  {row.get('code', ''):<8} {row.get('description', '')}")
    else:
        print(
            "\nNo partOfTerm codes came back for that term. Try again with "
            "--term set to a real term code (see vocab.json's 'terms' list)."
        )


def cmd_term(client, term, subject, course, out_dir, page_size):
    all_sections = []
    offset = 0
    while True:
        page = client.search(term, subject=subject, course=course, page_offset=offset, page_max=page_size)
        data = page.get("data") or []
        if not data:
            break
        all_sections.extend(data)
        print(f"  fetched {len(all_sections)} / {page.get('totalCount', '?')} sections...")
        if len(data) < page_size:
            break
        offset += page_size

    raw_path = os.path.join(out_dir, "raw_sections.json")
    with open(raw_path, "w") as f:
        json.dump(all_sections, f, indent=2)

    csv_path = os.path.join(out_dir, "candidates.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for section in all_sections:
            writer.writerow(flatten(section))

    print(f"\nWrote {len(all_sections)} section(s) to {raw_path} and {csv_path}")
    if not all_sections:
        print("No sections found - double check --term / --subject / --course.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--term", default="", help="Banner term code, e.g. 202710")
    parser.add_argument("--subject", default="", help="Filter to one subject, e.g. MATH")
    parser.add_argument("--course", default="", help="Filter to one course number, e.g. 104")
    parser.add_argument("--dump-vocab", action="store_true", help="Write vocab.json (subject/partOfTerm/campus/... codes)")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    host = os.environ.get("BANNER")
    if not host:
        sys.exit("Set BANNER to your school's Banner host first, e.g.:\n  export BANNER=ssb.cofc.edu")

    client = BannerClient(host)
    client.prime(args.term)

    if args.dump_vocab:
        cmd_dump_vocab(client, args.term, args.out_dir)
        return

    if not args.term:
        sys.exit("Pass --term 202710 (or similar) to enumerate sections, or use --dump-vocab first.")

    cmd_term(client, args.term, args.subject, args.course, args.out_dir, args.page_size)


if __name__ == "__main__":
    main()
