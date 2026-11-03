# test_watch.py - alert delivery and retry behaviour for watch.py. Network fully mocked.
# Usage: python -m unittest test_watch -v

import contextlib, io, json, os, tempfile, unittest
from unittest import mock
import requests
import watch

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


if __name__ == "__main__":
    unittest.main()
