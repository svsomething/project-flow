#!/usr/bin/env python3
"""
Tests for scripts/claude_runner.py.

Run with:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import claude_runner as cr  # noqa: E402


# The exact line from the 2026-06-22 incident (project-monitor.log:83166-83241),
# repeated for 16 cycles with nothing marking the run as broken.
INCIDENT_LINE = "Failed to authenticate. API Error: 401 Invalid authentication credentials"


def stub(tmpdir, name, body):
    """Write an executable shell stub standing in for the Claude CLI."""
    path = Path(tmpdir) / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return path


class DetectionTests(unittest.TestCase):
    def test_matches_the_real_incident_line(self):
        self.assertTrue(cr.detect_auth_failure(INCIDENT_LINE))

    def test_matches_every_listed_signature(self):
        for sig in cr.AUTH_SIGNATURES:
            self.assertTrue(cr.detect_auth_failure(f"prefix {sig} suffix"), sig)

    def test_is_case_insensitive(self):
        self.assertTrue(cr.detect_auth_failure(INCIDENT_LINE.upper()))

    def test_ignores_unrelated_output(self):
        self.assertFalse(cr.detect_auth_failure("Wrote 3 files. Done."))
        self.assertFalse(cr.detect_auth_failure(""))
        self.assertFalse(cr.detect_auth_failure(None))

    def test_excerpt_keeps_only_matching_lines(self):
        text = f"starting up\n{INCIDENT_LINE}\ntrailing noise"
        self.assertEqual(cr.auth_error_excerpt(text), INCIDENT_LINE)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

        # Isolate the breaker state file from the real one.
        self._real_state = cr.AUTH_STATE_FILE
        cr.AUTH_STATE_FILE = self.dir / "claude-auth-state.json"
        self.addCleanup(setattr, cr, "AUTH_STATE_FILE", self._real_state)

        self.logs = []
        self.posted = []
        # Notification goes through gh; record the calls instead of shelling out.
        self._real_post = cr._post_comment
        cr._post_comment = lambda target, body, env: (self.posted.append((target, body)), (True, ""))[1]
        self.addCleanup(setattr, cr, "_post_comment", self._real_post)

        self._real_alerted = cr._already_alerted
        cr._already_alerted = lambda target, env, bot_login: False
        self.addCleanup(setattr, cr, "_already_alerted", self._real_alerted)

    def run_stub(self, path, **kwargs):
        return cr.run_claude("prompt", os.environ.copy(),
                             claude_bin=path, log=self.logs.append, **kwargs)

    def error_lines(self):
        return [line for line in self.logs if "ERROR:" in line]

    # -- outcome classification ------------------------------------------

    def test_success_returns_ok(self):
        s = stub(self.dir, "ok", "echo 'wrote 3 files'; exit 0")
        self.assertEqual(self.run_stub(s), cr.OK)
        self.assertEqual(self.error_lines(), [])
        self.assertIsNone(cr.load_auth_state())

    def test_auth_error_on_exit_zero_is_still_auth_failed(self):
        """The case a returncode check alone would miss."""
        s = stub(self.dir, "auth0", f"echo '{INCIDENT_LINE}'; exit 0")
        self.assertEqual(self.run_stub(s), cr.AUTH_FAILED)
        self.assertTrue(self.error_lines())

    def test_auth_error_on_nonzero_exit_is_auth_failed(self):
        s = stub(self.dir, "auth1", f"echo '{INCIDENT_LINE}' >&2; exit 1")
        self.assertEqual(self.run_stub(s), cr.AUTH_FAILED)

    def test_nonzero_exit_with_unrelated_output_is_failed(self):
        s = stub(self.dir, "boom", "echo 'unrelated crash' >&2; exit 3")
        self.assertEqual(self.run_stub(s), cr.FAILED)
        self.assertTrue(any("exited with code 3" in line for line in self.error_lines()))
        # A generic failure must not trip the auth breaker.
        self.assertIsNone(cr.load_auth_state())

    def test_hang_past_timeout_is_killed_and_reported(self):
        s = stub(self.dir, "hang", "sleep 30")
        self.assertEqual(self.run_stub(s, timeout=1), cr.TIMEOUT)
        self.assertTrue(any("timed out" in line for line in self.error_lines()))

    def test_missing_binary_is_failed_not_a_crash(self):
        self.assertEqual(self.run_stub(self.dir / "does-not-exist"), cr.FAILED)

    def test_output_is_re_emitted_to_the_log(self):
        s = stub(self.dir, "chatty", "echo 'hello from claude'")
        self.run_stub(s)
        self.assertIn("  claude| hello from claude", self.logs)

    # -- circuit breaker --------------------------------------------------

    def test_breaker_skips_subsequent_invocations(self):
        auth  = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        canary = self.dir / "ran"
        never = stub(self.dir, "never", f"touch {canary}; exit 0")

        self.assertEqual(self.run_stub(auth), cr.AUTH_FAILED)
        for _ in range(3):
            self.assertEqual(self.run_stub(never), cr.SKIPPED)
        self.assertFalse(canary.exists(), "breaker let an invocation through")
        self.assertTrue(any("SKIP: Claude auth broken since" in line for line in self.logs))

    def test_probe_is_let_through_after_the_retry_interval(self):
        auth = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        ok   = stub(self.dir, "ok", "echo done; exit 0")
        self.run_stub(auth)

        # Rewind the clock past the backoff window.
        state = cr.load_auth_state()
        state["last_attempt"] = cr._ts(cr._now() - timedelta(seconds=cr.AUTH_RETRY_INTERVAL + 60))
        cr.AUTH_STATE_FILE.write_text(__import__("json").dumps(state))

        self.assertEqual(self.run_stub(ok), cr.OK)
        self.assertIsNone(cr.load_auth_state(), "recovery must clear the breaker")
        self.assertTrue(any("RECOVERED" in line for line in self.logs))

    def test_failed_probe_re_arms_the_breaker(self):
        auth = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        self.run_stub(auth)
        first_failed_at = cr.load_auth_state()["failed_at"]

        state = cr.load_auth_state()
        state["last_attempt"] = cr._ts(cr._now() - timedelta(seconds=cr.AUTH_RETRY_INTERVAL + 60))
        cr.AUTH_STATE_FILE.write_text(__import__("json").dumps(state))

        self.assertEqual(self.run_stub(auth), cr.AUTH_FAILED)
        # Still open, and the original outage start time is preserved.
        self.assertEqual(cr.load_auth_state()["failed_at"], first_failed_at)
        self.assertEqual(self.run_stub(auth), cr.SKIPPED)

    # -- notification -----------------------------------------------------

    def test_alert_is_posted_once_across_many_cycles(self):
        auth   = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        target = {"repo": "svsomething/project-flow", "number": 27}

        for _ in range(5):
            self.run_stub(auth, target=target, bot_login="svsomething-bot")

        self.assertEqual(len(self.posted), 1)
        _, body = self.posted[0]
        self.assertTrue(body.startswith(cr.ALERT_HEADING))
        self.assertIn(INCIDENT_LINE, body)
        self.assertIn("re-authenticate", body)

    def test_recovery_replies_to_every_alerted_card(self):
        auth = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        ok   = stub(self.dir, "ok", "echo done; exit 0")
        target = {"repo": "svsomething/project-flow", "number": 27}

        self.run_stub(auth, target=target, bot_login="svsomething-bot")
        self.assertEqual(len(self.posted), 1)

        state = cr.load_auth_state()
        state["last_attempt"] = cr._ts(cr._now() - timedelta(seconds=cr.AUTH_RETRY_INTERVAL + 60))
        cr.AUTH_STATE_FILE.write_text(__import__("json").dumps(state))

        self.assertEqual(self.run_stub(ok), cr.OK)
        self.assertEqual(len(self.posted), 2)
        recovery_target, recovery_body = self.posted[1]
        self.assertEqual(recovery_target, target)
        self.assertTrue(recovery_body.startswith(cr.RESUME_HEADING))

        # State cleared, so a future outage can notify again.
        self.run_stub(auth, target=target, bot_login="svsomething-bot")
        self.assertEqual(len(self.posted), 3)

    def test_existing_alert_comment_suppresses_a_duplicate(self):
        cr._already_alerted = lambda target, env, bot_login: True
        auth   = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        target = {"repo": "svsomething/project-flow", "number": 27}
        self.run_stub(auth, target=target, bot_login="svsomething-bot")
        self.assertEqual(self.posted, [])

    def test_no_target_means_no_comment_but_still_an_error_log(self):
        auth = stub(self.dir, "auth", f"echo '{INCIDENT_LINE}'; exit 1")
        self.assertEqual(self.run_stub(auth), cr.AUTH_FAILED)
        self.assertEqual(self.posted, [])
        self.assertTrue(self.error_lines())


if __name__ == "__main__":
    unittest.main()
