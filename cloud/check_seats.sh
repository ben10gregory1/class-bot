#!/usr/bin/env bash
# Single-shot CofC open-seat check for GitHub Actions (or any cron host).
# Pushes an ntfy alert if any watched section has an open seat.
set -euo pipefail

BASE="https://ssb.cofc.edu/StudentRegistrationSsb/ssb"
TERM="${TERM_CODE:-202710}"      # 202710 = Fall 2026
SUBJECT="${SUBJECT:-MATH}"
COURSE="${COURSE:-104}"
TOPIC="${NTFY_TOPIC:?NTFY_TOPIC env var is required}"
LINK="$BASE/term/termSelection?mode=search"
JAR="$(mktemp)"

# 1) prime session  2) set term  3) search
curl -s -c "$JAR" -b "$JAR" -o /dev/null --max-time 25 "$BASE/term/termSelection?mode=search"
curl -s -c "$JAR" -b "$JAR" -o /dev/null --max-time 25 -X POST "$BASE/term/search?mode=search" \
  --data-urlencode "term=$TERM" --data-urlencode "studyPath=" \
  --data-urlencode "startDatepicker=" --data-urlencode "endDatepicker="
JSON="$(curl -s -c "$JAR" -b "$JAR" --max-time 25 \
  "$BASE/searchResults/searchResults?txt_subject=$SUBJECT&txt_courseNumber=$COURSE&txt_term=$TERM&pageOffset=0&pageMaxSize=100&sortColumn=subjectDescription&sortDirection=asc")"

TOTAL="$(echo "$JSON" | jq -r '.totalCount // 0')"
OPEN="$(echo "$JSON" | jq -r '.data[]? | select(.seatsAvailable > 0)
  | "\(.subject) \(.courseNumber)-\(.sequenceNumber) (CRN \(.courseReferenceNumber)): \(.seatsAvailable) seat(s)"')"

if [ -n "$OPEN" ]; then
  echo "OPEN SEATS FOUND:"
  echo "$OPEN"
  BODY="$OPEN
Register: $LINK"
  curl -s -o /dev/null \
    -H "Title: SEAT OPEN - $SUBJECT $COURSE" \
    -H "Priority: urgent" \
    -H "Tags: rotating_light" \
    -d "$BODY" "https://ntfy.sh/$TOPIC"
  echo "Alert pushed to ntfy topic: $TOPIC"
else
  echo "Checked $TOTAL sections of $SUBJECT $COURSE ($TERM) - none open."
fi
