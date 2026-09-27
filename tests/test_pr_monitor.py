#!/usr/bin/env python3
"""
Tests for failed-lookup handling in scripts/pr-monitor.

Run with:  python3 -m unittest discover -s tests -v
"""

import importlib.machinery
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_pr_monitor():
    """Import `pr-monitor` (no .py extension, so name the loader explicitly)."""
    path = str(SCRIPTS / "pr-monitor")
    spec = importlib.util.spec_from_file_location(
        "pr_monitor", path,
        loader=importlib.machinery.SourceFileLoader("pr_monitor", path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prm = _load_pr_monitor()

CFG = {"github": {"bot_login": "bot", "org": "owner", "bot_token_file": "/nonexistent"},
       "repos": {"root": "/nonexistent"}}
REPO = "/repos/infra"
OTHER = "/repos/other"


class PrMonitorTestCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.state_file = tmp / "state.json"
        patches = [
            mock.patch.object(prm, "STATE_FILE", self.state_file),
            mock.patch.object(prm, "LOCK_FILE", tmp / "lock"),
            mock.patch.object(prm, "load_config", return_value=CFG),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def write_state(self, entries):
        self.state_file.write_text(json.dumps(entries))

    def read_state(self):
        return json.loads(self.state_file.read_text())

    def run_main(self, repos, run_side_effect):
        """Run main() over `repos`, with prm.run replaced. Returns (run mock, log output)."""
        out = io.StringIO()
        with mock.patch.object(prm, "find_repos", return_value=set(repos)), \
             mock.patch.object(prm, "run", side_effect=run_side_effect) as run, \
             redirect_stdout(out):
            prm.main()
        return run, out.getvalue()


def pr_list_calls(run):
    return [c for c in run.call_args_list if c.args[0][:3] == ["gh", "pr", "list"]]


def failing_run(cmd, cfg, cwd=None):
    raise RuntimeError(f"{cmd}: GraphQL: Could not resolve to a Repository")


class FailedLookupTests(PrMonitorTestCase):
    def test_failed_listing_keeps_state_entries(self):
        entries = [{"repo": REPO, "pr": 7}, {"repo": REPO, "pr": 8}]
        self.write_state(entries)
        self.run_main([REPO], failing_run)
        self.assertEqual(self.read_state(), entries)

    def test_failed_listing_logs_once(self):
        self.write_state([{"repo": REPO, "pr": 7}])
        _, out = self.run_main([REPO], failing_run)
        self.assertEqual(out.count("Could not list PRs in infra"), 1)

    def test_listing_runs_once_per_repo(self):
        self.write_state([{"repo": REPO, "pr": 7}])
        run, _ = self.run_main([REPO, OTHER], lambda cmd, cfg, cwd=None: "[]")
        self.assertEqual(sorted(c.kwargs["cwd"] for c in pr_list_calls(run)),
                         sorted([REPO, OTHER]))

    def test_empty_listing_still_cleans_up_merged(self):
        self.write_state([{"repo": REPO, "pr": 7}, {"repo": OTHER, "pr": 3}])
        self.run_main([REPO], lambda cmd, cfg, cwd=None: "[]")
        self.assertEqual(self.read_state(), [{"repo": OTHER, "pr": 3}])


class CleanupMergedTests(PrMonitorTestCase):
    def test_none_is_a_noop(self):
        entries = [{"repo": REPO, "pr": 7}]
        self.write_state(entries)
        prm.cleanup_merged(REPO, None)
        self.assertEqual(self.read_state(), entries)

    def test_keeps_open_drops_closed(self):
        self.write_state([{"repo": REPO, "pr": 7}, {"repo": REPO, "pr": 8}])
        with redirect_stdout(io.StringIO()):
            prm.cleanup_merged(REPO, [{"number": 8}])
        self.assertEqual(self.read_state(), [{"repo": REPO, "pr": 8}])


if __name__ == "__main__":
    unittest.main()
