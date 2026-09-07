#!/usr/bin/env python3
"""
Tests for the in-flight guards in scripts/project-monitor.

Run with:  python3 -m unittest discover -s tests -v
"""

import importlib.machinery
import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import claude_runner as cr  # noqa: E402


def _load_project_monitor():
    """Import `project-monitor`.

    It has no .py extension, so the import machinery cannot infer a loader from
    the path — SourceFileLoader has to be named explicitly.
    """
    path = str(SCRIPTS / "project-monitor")
    spec = importlib.util.spec_from_file_location(
        "project_monitor", path,
        loader=importlib.machinery.SourceFileLoader("project_monitor", path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pm = _load_project_monitor()

NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def ts(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def comment(body, minutes_ago=1):
    return {"body": body, "createdAt": ts(minutes_ago)}


def state(comments, start, finish):
    return pm.in_flight_state(comments, start, finish, now=NOW)[0]


def impl_state(comments):
    return state(comments, pm.IMPL_START_MARKERS, pm.IMPL_FINISH_MARKERS)


def done_state(comments):
    return state(comments, pm.DONE_START_MARKERS, pm.DONE_FINISH_MARKERS)


def plan_state(comments):
    return state(comments, pm.PLAN_START_MARKERS, pm.PLAN_FINISH_MARKERS)


# The shape that actually broke #27 on 2026-09-07: a plan discussing the guards
# and quoting every marker phrase in prose, on a card no run had ever touched.
PLAN_QUOTING_MARKERS = f"""{pm.PLAN_FINISH}
## Plan

The guard at `project-monitor:208` tests `"Starting implementation" in body`,
so this very comment used to trip it. The done guard matches `## Merging PRs`
or `## Done` the same way, and `## Implementation complete` never clears it.
"""

# The residual hole that plain anchoring (`^## Done`, multiline) leaves open:
# a plan is Markdown, and a plan may legitimately use a marker as a heading.
PLAN_WITH_MARKER_HEADINGS = f"""{pm.PLAN_FINISH}
## Plan

Step one, then:

## Done

Wrap up and move the card.

## Merging PRs

Squash each one.
"""


class InFlightMatching(unittest.TestCase):
    """A marker only counts on the first line of a comment."""

    def test_plan_quoting_markers_inline_is_clear(self):
        self.assertEqual(impl_state([comment(PLAN_QUOTING_MARKERS)]), pm.CLEAR)
        self.assertEqual(done_state([comment(PLAN_QUOTING_MARKERS)]), pm.CLEAR)

    def test_plan_using_markers_as_headings_is_clear(self):
        self.assertEqual(impl_state([comment(PLAN_WITH_MARKER_HEADINGS)]), pm.CLEAR)
        self.assertEqual(done_state([comment(PLAN_WITH_MARKER_HEADINGS)]), pm.CLEAR)

    def test_no_comments_is_clear(self):
        self.assertEqual(impl_state([]), pm.CLEAR)

    def test_leading_whitespace_still_matches(self):
        body = f"\n  {pm.IMPL_START}\n## Starting implementation"
        self.assertEqual(impl_state([comment(body, 5)]), pm.RUNNING)

    def test_retry_notice_does_not_set_state(self):
        self.assertEqual(impl_state([comment(f"{pm.RETRY}\n## ♻️ Retrying a stale run")]),
                         pm.CLEAR)

    def test_auth_alert_does_not_set_state(self):
        alert = f"{cr.ALERT_SENTINEL}\n{cr.ALERT_HEADING}\n\nRun `claude` on the host."
        self.assertEqual(impl_state([comment(alert)]), pm.CLEAR)
        self.assertEqual(plan_state([comment(alert)]), pm.CLEAR)


class InFlightStaleness(unittest.TestCase):
    """An unmatched start marker expires so a dead run is retried, not stuck."""

    def test_recent_start_is_running(self):
        self.assertEqual(impl_state([comment(pm.IMPL_START, 5)]), pm.RUNNING)

    def test_old_start_is_stale(self):
        self.assertEqual(impl_state([comment(pm.IMPL_START, 90)]), pm.STALE)

    def test_start_then_finish_is_clear(self):
        self.assertEqual(impl_state([
            comment(pm.IMPL_START, 90),
            comment(pm.IMPL_FINISH, 89),
        ]), pm.CLEAR)

    def test_finish_before_start_does_not_clear(self):
        """A retry cycle: the old finish must not satisfy the newer start."""
        self.assertEqual(impl_state([
            comment(pm.IMPL_START, 300),
            comment(pm.IMPL_FINISH, 290),
            comment(pm.IMPL_START, 5),
        ]), pm.RUNNING)

    def test_stale_returns_the_offending_comment(self):
        started = comment(pm.IMPL_START, 90)
        result, start = pm.in_flight_state(
            [started], pm.IMPL_START_MARKERS, pm.IMPL_FINISH_MARKERS, now=NOW)
        self.assertEqual(result, pm.STALE)
        self.assertEqual(start["createdAt"], started["createdAt"])

    def test_unordered_input_is_sorted(self):
        self.assertEqual(impl_state([
            comment(pm.IMPL_FINISH, 89),
            comment(pm.IMPL_START, 90),
        ]), pm.CLEAR)

    def test_stale_threshold_clears_the_run_timeout(self):
        """Raising TIMEOUT_SECONDS past 30 min must fail here, not in production.

        A start marker older than STALE_AFTER is only *provably* dead because the
        invocation that posted it is killed at TIMEOUT_SECONDS and releases the
        PID lock. Without margin, a still-running card could be declared stale
        and re-dispatched.
        """
        self.assertGreaterEqual(pm.STALE_AFTER.total_seconds(),
                                2 * cr.TIMEOUT_SECONDS)


class LegacyMarkers(unittest.TestCase):
    """Cards carrying pre-sentinel markers keep their state across the deploy."""

    def test_legacy_visible_heading_is_recognised(self):
        self.assertEqual(impl_state([comment(pm.LEGACY_IMPL_START, 5)]), pm.RUNNING)
        self.assertEqual(done_state([comment(pm.LEGACY_DONE_START, 5)]), pm.RUNNING)

    def test_legacy_start_cleared_by_sentinel_finish(self):
        self.assertEqual(impl_state([
            comment(pm.LEGACY_IMPL_START, 90),
            comment(pm.IMPL_FINISH, 89),
        ]), pm.CLEAR)

    def test_legacy_done_finish_clears_legacy_done_start(self):
        self.assertEqual(done_state([
            comment(pm.LEGACY_DONE_START, 90),
            comment(pm.LEGACY_DONE_FINISH, 89),
        ]), pm.CLEAR)


class PlanSlot(unittest.TestCase):
    """Which bot comments count as "a plan exists" for the plan/iterate split."""

    def test_plan_comment_counts(self):
        self.assertTrue(pm.is_plan_comment(comment(PLAN_QUOTING_MARKERS)))

    def test_legacy_plan_without_sentinel_counts(self):
        self.assertTrue(pm.is_plan_comment(comment("## Plan\n\nDo the thing.")))

    def test_plan_start_marker_is_not_a_plan(self):
        """Otherwise a dead plan run parks the card in the iterate branch."""
        self.assertFalse(pm.is_plan_comment(comment(f"{pm.PLAN_START}\n## Planning")))

    def test_auth_alert_is_not_a_plan(self):
        """The bug behind the old "any bot comment" test: an auth alert on a Plan
        card made bot_comments non-empty, so the card was never planned."""
        self.assertFalse(pm.is_plan_comment(
            comment(f"{cr.ALERT_SENTINEL}\n{cr.ALERT_HEADING}")))
        self.assertFalse(pm.is_plan_comment(comment(cr.ALERT_HEADING)))
        self.assertFalse(pm.is_plan_comment(comment(cr.RESUME_HEADING)))

    def test_retry_notice_is_not_a_plan(self):
        self.assertFalse(pm.is_plan_comment(comment(f"{pm.RETRY}\n## ♻️ Retrying")))

    def test_implement_markers_are_not_plans(self):
        self.assertFalse(pm.is_plan_comment(comment(pm.LEGACY_IMPL_START)))
        self.assertFalse(pm.is_plan_comment(comment(pm.LEGACY_DONE_FINISH)))


class Timestamps(unittest.TestCase):
    def test_z_suffix_is_parsed_as_utc(self):
        self.assertEqual(pm.parse_ts("2026-09-07T12:00:00Z"), NOW)

    def test_naive_timestamp_is_assumed_utc(self):
        self.assertEqual(pm.parse_ts("2026-09-07T12:00:00"), NOW)


if __name__ == "__main__":
    unittest.main()
