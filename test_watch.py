# test_watch.py - alert delivery and retry behaviour for watch.py. Network fully mocked.
# Usage: python -m unittest test_watch -v

import contextlib, io, json, os, tempfile, unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
import requests
import plans
import watch
import watchdog

TOPIC = "fake-topic-for-tests"
CFG = {"term": "202720", "watch": [{"crns": ["A", "B"], "label": "test"}]}


def sec(crn, seats):
    return {"courseReferenceNumber": crn, "seatsAvailable": seats, "subject": "ACCT",
            "courseNumber": "203", "sequenceNumber": "01", "courseTitle": "Accounting",
            "faculty": [], "partOfTerm": "1"}


def resp(status):
    return mock.Mock(status_code=status)


class WatchTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for p in (mock.patch.dict(os.environ, {"NTFY_TOPIC": TOPIC}),
                  mock.patch.object(watch, "STATE", os.path.join(tmp.name, "state.json")),
                  mock.patch.object(watch, "session"),
                  mock.patch.object(watch, "classify", return_value="ASYNC")):
            p.start()
            self.addCleanup(p.stop)
        self.stderr = io.StringIO()

    def poll(self, secs, post_effect):
        """One pass in a fresh 'run': state comes from disk, as after an Actions checkout."""
        effect = post_effect if isinstance(post_effect, list) else [post_effect]
        with mock.patch.object(watch, "fetch_all", return_value=secs), \
                mock.patch.object(watch.requests, "post", side_effect=effect) as post, \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(self.stderr):
            watch.one_pass(CFG, watch.load_state())
        return post

    def saved(self):
        with open(watch.STATE) as f:
            return json.load(f)

    def test_success_records_open_and_does_not_realert(self):
        post = self.poll([sec("A", 2)], resp(200))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.saved()["A"], {"open": True, "seats": 2})
        post = self.poll([sec("A", 2)], resp(200))
        self.assertEqual(post.call_count, 0)

    def test_http_500_stays_unrecorded(self):
        self.poll([sec("A", 2)], resp(500))
        self.assertEqual(self.saved()["A"], {"open": False, "seats": 2})
        self.assertIn("HTTP 500", self.stderr.getvalue())

    def test_redirect_status_is_not_delivery(self):
        self.poll([sec("A", 2)], resp(302))
        self.assertFalse(self.saved()["A"]["open"])

    def test_connection_error_stays_unrecorded(self):
        self.poll([sec("A", 2)], requests.ConnectionError("boom"))
        self.assertEqual(self.saved()["A"], {"open": False, "seats": 2})

    def test_timeout_stays_unrecorded(self):
        self.poll([sec("A", 2)], requests.Timeout("slow"))
        self.assertFalse(self.saved()["A"]["open"])

    def test_retry_across_runs_then_stops_after_success(self):
        self.assertEqual(self.poll([sec("A", 2)], resp(500)).call_count, 1)
        self.assertEqual(self.poll([sec("A", 2)], requests.ConnectionError("boom")).call_count, 1)
        self.assertEqual(self.poll([sec("A", 2)], resp(200)).call_count, 1)
        self.assertTrue(self.saved()["A"]["open"])
        self.assertEqual(self.poll([sec("A", 2)], resp(200)).call_count, 0)

    def test_failed_send_does_not_block_other_targets(self):
        post = self.poll([sec("A", 1), sec("B", 1)], [requests.ConnectionError("boom"), resp(200)])
        self.assertEqual(post.call_count, 2)
        st = self.saved()
        self.assertFalse(st["A"]["open"])
        self.assertTrue(st["B"]["open"])

    def test_seat_closed_before_retry_sends_nothing(self):
        self.poll([sec("A", 2)], resp(500))
        post = self.poll([sec("A", 0)], resp(200))
        self.assertEqual(post.call_count, 0)
        self.assertEqual(self.saved()["A"], {"open": False, "seats": 0})

    def test_closed_seat_never_alerts(self):
        post = self.poll([sec("A", 0)], resp(200))
        self.assertEqual(post.call_count, 0)

    def test_reopen_after_close_alerts_again(self):
        self.poll([sec("A", 2)], resp(200))
        self.poll([sec("A", 0)], resp(200))
        self.assertEqual(self.poll([sec("A", 3)], resp(200)).call_count, 1)

    def test_failure_log_never_contains_topic(self):
        err = requests.ConnectionError(f"Max retries exceeded with url: /{TOPIC}")
        self.poll([sec("A", 2)], err)
        self.assertIn("ConnectionError", self.stderr.getvalue())
        self.assertNotIn(TOPIC, self.stderr.getvalue())

    def test_unset_topic_is_still_fatal(self):
        with mock.patch.dict(os.environ):
            del os.environ["NTFY_TOPIC"]
            with self.assertRaises(SystemExit):
                watch.notify(CFG, "t", "b", "u")
            with self.assertRaises(SystemExit):
                watch.main()


def psec(crn, seats, course="ACCT 203", days=("monday",), begin="1000", end="1050", wait=0, part="1"):
    subject, number = course.split()
    meeting = {"beginTime": begin, "endTime": end, **{d: True for d in days}}
    return {"courseReferenceNumber": crn, "seatsAvailable": seats, "subject": subject,
            "courseNumber": number, "sequenceNumber": "01", "courseTitle": course, "faculty": [],
            "partOfTerm": part, "creditHourLow": 3, "waitCount": wait,
            "meetingsFaculty": [{"meetingTime": meeting}]}


def rungs(*crns):
    return [{"crn": c, "why": f"why {c}"} for c in crns]


PLANS = {"minCredits": 6, "registered": [], "blocked": [],
         "slots": [{"course": "ACCT 203", "rungs": rungs("A1", "A2", "A3")},
                   {"course": "MATH 104", "rungs": rungs("M1", "M2", "M3")}],
         "bench": [{"course": "POLI 101", "rungs": rungs("P1")}]}


def pool(**seats):
    """All sections at distinct times unless a test builds its own."""
    base = {"A1": 5, "A2": 5, "A3": 5, "M1": 5, "M2": 5, "M3": 5, "P1": 5, **seats}
    hours = {"A1": "0800", "A2": "0900", "A3": "1000", "M1": "1100", "M2": "1200", "M3": "1300", "P1": "1400"}
    courses = {"A": "ACCT 203", "M": "MATH 104", "P": "POLI 101"}
    return [psec(c, n, courses[c[0]], begin=hours[c], end=str(int(hours[c]) + 50).zfill(4))
            for c, n in base.items()]


class ResolveTest(unittest.TestCase):
    def picks(self, secs, **over):
        result = plans.resolve({**PLANS, **over}, {s["courseReferenceNumber"]: s for s in secs})
        return {p["course"]: p["crn"] for p in result["picks"]}, result["credits"]

    def test_all_open_is_plan_a(self):
        self.assertEqual(self.picks(pool())[0], {"ACCT 203": "A1", "MATH 104": "M1"})

    def test_full_section_falls_to_next_rung(self):
        self.assertEqual(self.picks(pool(A1=0))[0]["ACCT 203"], "A2")
        self.assertEqual(self.picks(pool(A1=0, A2=0))[0]["ACCT 203"], "A3")

    def test_negative_seats_are_full(self):
        self.assertEqual(self.picks(pool(A1=-2))[0]["ACCT 203"], "A2")

    def test_seat_held_by_waitlist_is_not_available(self):
        secs = [psec("A1", 2, wait=1, begin="0800", end="0850"), psec("A2", 2, begin="0900", end="0950")]
        self.assertEqual(self.picks(secs)[0]["ACCT 203"], "A2")

    def test_clash_moves_the_lower_priority_course(self):
        secs = [psec("A1", 5, begin="1000", end="1050"),
                psec("M1", 5, "MATH 104", begin="1000", end="1050"),
                psec("M2", 5, "MATH 104", begin="1100", end="1150")]
        self.assertEqual(self.picks(secs)[0], {"ACCT 203": "A1", "MATH 104": "M2"})

    def test_tue_and_thu_do_not_clash(self):
        a, b = psec("A1", 5, days=("tuesday",)), psec("M1", 5, "MATH 104", days=("thursday",))
        self.assertFalse(plans.clash(a, b))
        self.assertEqual(self.picks([a, b])[1], 6)

    def test_express_terms_do_not_clash(self):
        self.assertFalse(plans.clash(psec("A1", 5, part="2"), psec("M1", 5, "MATH 104", part="3")))

    def test_slot_out_of_options_uses_bench_to_hold_credit_floor(self):
        picks, credits = self.picks(pool(M1=0, M2=0, M3=0))
        self.assertIsNone(picks["MATH 104"])
        self.assertEqual(picks["POLI 101"], "P1")
        self.assertEqual(credits, 6)

    def test_bench_stays_off_when_floor_is_met(self):
        self.assertNotIn("POLI 101", self.picks(pool())[0])

    def test_blocked_window_skips_a_rung(self):
        blocked = [{"days": "M", "start": "0800", "end": "0850"}]
        self.assertEqual(self.picks(pool(), blocked=blocked)[0]["ACCT 203"], "A2")

    def test_registered_section_holds_even_at_zero_seats(self):
        self.assertEqual(self.picks(pool(A1=0), registered=["A1"])[0]["ACCT 203"], "A1")


class PlanAlertTest(unittest.TestCase):
    def setUp(self):
        self.st, self.sent = {}, []

    def run_check(self, secs, ok=True, cfg=PLANS, watched=()):
        self.sent.clear()
        plans.check(cfg, secs, self.st, lambda t, b, p: self.sent.append((t, b, p)) or ok, watched)
        return [t for t, _, _ in self.sent]

    def test_plan_a_on_first_run_is_quiet(self):
        self.assertEqual(self.run_check(pool()), [])

    def test_change_alerts_once_and_says_why(self):
        self.assertEqual(self.run_check(pool(A1=0)), ["PLAN CHANGE: ACCT 203"])
        self.assertIn("why A2", self.sent[0][1])
        self.assertEqual(self.run_check(pool(A1=0)), [])

    def test_reopened_plan_a_alerts_back(self):
        self.run_check(pool(A1=0))
        self.assertEqual(self.run_check(pool()), ["PLAN CHANGE: ACCT 203"])

    def test_failed_change_alert_retries(self):
        self.run_check(pool(A1=0), ok=False)
        self.assertEqual(self.run_check(pool(A1=0)), ["PLAN CHANGE: ACCT 203"])
        self.assertEqual(self.run_check(pool(A1=0)), [])

    def test_under_floor_is_called_out(self):
        secs = [s for s in pool(M1=0, M2=0, M3=0) if s["courseReferenceNumber"] != "P1"]
        self.run_check(secs)
        self.assertIn("UNDER the 6 cr floor", self.sent[0][1])

    def test_backup_last_seat_flags_once_at_default_priority(self):
        self.run_check(pool())
        self.assertEqual(self.run_check(pool(A2=1)), ["LAST SEAT: ACCT 203 CRN A2 (backup)"])
        self.assertEqual(self.sent[0][2], "default")
        self.assertEqual(self.run_check(pool(A2=1)), [])

    def test_current_pick_last_seat_is_urgent(self):
        self.run_check(pool())
        self.run_check(pool(A1=1))
        self.assertEqual(self.sent[0][2], "urgent")

    def test_last_seat_fires_again_after_refill(self):
        self.run_check(pool(A2=1))
        self.run_check(pool(A2=3))
        self.assertEqual(self.run_check(pool(A2=1)), ["LAST SEAT: ACCT 203 CRN A2 (backup)"])

    def test_failed_last_seat_retries(self):
        self.run_check(pool(A2=1), ok=False)
        self.assertEqual(self.run_check(pool(A2=1)), ["LAST SEAT: ACCT 203 CRN A2 (backup)"])

    def test_registered_and_watched_sections_are_skipped(self):
        cfg = {**PLANS, "registered": ["A1"]}
        self.assertEqual(self.run_check(pool(A1=1, M1=1), cfg=cfg, watched={"M1"}), [])


class WatchLastSeatTest(WatchTest):
    def test_drop_to_one_seat_flags_once(self):
        self.poll([sec("A", 4)], resp(200))
        post = self.poll([sec("A", 1)], resp(200))
        self.assertEqual(post.call_count, 1)
        self.assertIn("LAST SEAT", post.call_args.kwargs["headers"]["Title"])
        self.assertEqual(self.poll([sec("A", 1)], resp(200)).call_count, 0)

    def test_opening_with_one_seat_is_one_alert_marked_last_seat(self):
        post = self.poll([sec("A", 1)], resp(200))
        self.assertEqual(post.call_count, 1)
        self.assertIn("LAST SEAT", post.call_args.kwargs["headers"]["Title"])

    def test_failed_last_seat_retries_next_poll(self):
        self.poll([sec("A", 4)], resp(200))
        self.poll([sec("A", 1)], resp(500))
        self.assertEqual(self.saved()["A"]["seats"], 4)
        self.assertEqual(self.poll([sec("A", 1)], resp(200)).call_count, 1)


class WatchdogTest(unittest.TestCase):
    NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

    def check(self, minutes_ago):
        latest = None if minutes_ago is None else self.NOW - timedelta(minutes=minutes_ago)
        with mock.patch.object(watchdog, "latest_dispatch", return_value=latest):
            return watchdog.check(self.NOW)

    def test_recent_dispatch_is_quiet(self):
        self.assertIsNone(self.check(59))

    def test_stale_dispatch_alerts(self):
        self.assertIn("3.0 h", self.check(180))

    def test_no_dispatch_runs_alerts(self):
        self.assertIn("No Worker", self.check(None))

    def run_main(self, config, post_effect=None):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "config.json"), "w") as f:
                json.dump(config, f)
            cwd = os.getcwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, cwd)
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"NTFY_TOPIC": TOPIC}), \
                    mock.patch.object(watchdog, "latest_dispatch", return_value=None), \
                    mock.patch.object(watchdog.requests, "post", side_effect=post_effect,
                                      return_value=resp(200)) as post, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                watchdog.main()
            os.chdir(cwd)
        return post, err.getvalue()

    def test_off_by_default_sends_nothing(self):
        post, _ = self.run_main({})
        self.assertEqual(post.call_count, 0)

    def test_enabled_and_stale_pings(self):
        post, _ = self.run_main({"dispatchWatchdog": True})
        self.assertEqual(post.call_count, 1)

    def test_failed_ping_never_raises_or_logs_topic(self):
        err_obj = requests.ConnectionError(f"Max retries exceeded with url: /{TOPIC}")
        _, err = self.run_main({"dispatchWatchdog": True}, post_effect=err_obj)
        self.assertIn("ConnectionError", err)
        self.assertNotIn(TOPIC, err)


class FetchWatchedTest(unittest.TestCase):
    def fetch(self, targets, results):
        """results maps subject (None = full scan) to the sections Banner returns."""
        def fake(s, term, **filters):
            return results[filters.get("txt_subject")]
        with mock.patch.object(watch, "fetch_all", side_effect=fake) as fetch, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            secs = watch.fetch_watched(None, "202720", targets)
        return secs, fetch, err.getvalue()

    def test_queries_each_course_once_and_never_full_scans(self):
        targets = [{"subject": "ACCT", "courseNumber": "203", "crns": ["A"]},
                   {"subject": "ACCT", "courseNumber": "203", "crns": ["B"]},
                   {"subject": "MATH", "courseNumber": "104", "crns": ["C"]}]
        secs, fetch, _ = self.fetch(targets, {"ACCT": [sec("A", 0), sec("B", 0)], "MATH": [sec("C", 0)]})
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[0].kwargs,
                         {"txt_subject": "ACCT", "txt_courseNumber": "203"})
        self.assertEqual(len(secs), 3)

    def test_target_without_subject_full_scans(self):
        _, fetch, _ = self.fetch([{"crns": ["A"]}], {None: [sec("A", 0)]})
        self.assertEqual(fetch.call_args.kwargs, {})

    def test_wildcard_subject_full_scans(self):
        _, fetch, _ = self.fetch([{"subject": "*"}], {None: []})
        self.assertEqual(fetch.call_args.kwargs, {})

    def test_missing_crn_falls_back_to_full_scan_and_warns(self):
        targets = [{"subject": "ACCT", "courseNumber": "203", "crns": ["A"]}]
        secs, fetch, err = self.fetch(targets, {"ACCT": [], None: [sec("A", 1)]})
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(secs[0]["courseReferenceNumber"], "A")
        self.assertIn("A", err)


if __name__ == "__main__":
    unittest.main()
