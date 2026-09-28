#!/usr/bin/env python3
"""
Tests for scripts/pr-monitor: failed-lookup handling and post-merge steps.

Run with:  python3 -m unittest discover -s tests -v
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
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


# ── Post-merge ────────────────────────────────────────────────────────────────

CASE_B_BODY = """## Summary
- stuff

## Post-merge
- run: `cp a b && docker restart homeassistant`
- run: `cd x && docker compose up -d`

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
"""

CASE_A_BODY = """## Summary
- docs only

## Post-merge
No post-merge actions required — self-contained repo change, no services to restart.
"""

# The pr-workflow template keeps its example steps inside an HTML comment.
TEMPLATE_BODY = """## Post-merge
<!-- ALWAYS populate this section.
     CASE B — post-merge actions exist:
       - pull: `~/repos/project-flow`
       - run: `docker restart homeassistant`
-->
No post-merge actions required — nothing to deploy.
"""


class ParsePostMergeTests(unittest.TestCase):
    def test_run_steps_backticks_stripped(self):
        self.assertEqual(prm.parse_post_merge(CASE_B_BODY), [
            ("run", "cp a b && docker restart homeassistant"),
            ("run", "cd x && docker compose up -d"),
        ])

    def test_no_actions_sentence_yields_nothing(self):
        self.assertEqual(prm.parse_post_merge(CASE_A_BODY), [])

    def test_steps_inside_html_comment_are_ignored(self):
        self.assertEqual(prm.parse_post_merge(TEMPLATE_BODY), [])

    def test_missing_section_or_body(self):
        self.assertEqual(prm.parse_post_merge("## Summary\n- run: `rm -rf x`\n"), [])
        self.assertEqual(prm.parse_post_merge(None), [])

    def test_pull_multiple_paths_manual_and_unknown(self):
        body = ("## Post-merge\n"
                "- pull: `~/repos/project-flow` `~/repos/infra`\n"
                "- manual: rename the device in HA\n"
                "- restart the router\n")
        self.assertEqual(prm.parse_post_merge(body), [
            ("pull", ["~/repos/project-flow", "~/repos/infra"]),
            ("manual", "rename the device in HA"),
            ("unknown", "restart the router"),
        ])

    def test_section_ends_at_next_heading(self):
        body = "## Post-merge\n- run: `true`\n## Notes\n- run: `false`\n"
        self.assertEqual(prm.parse_post_merge(body), [("run", "true")])


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class GitRepoTestCase(unittest.TestCase):
    """A bare origin with `main`, plus a clone left on a merged feature branch."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        seed, self.origin, self.clone = tmp / "seed", tmp / "origin.git", tmp / "clone"
        git(tmp, "init", "-q", "-b", "main", str(seed))
        for args in (("config", "user.email", "t@t"), ("config", "user.name", "t")):
            git(seed, *args)
        (seed / "config.yaml").write_text("old\n")
        git(seed, "add", ".")
        git(seed, "commit", "-q", "-m", "init")
        git(tmp, "clone", "-q", "--bare", str(seed), str(self.origin))
        git(tmp, "clone", "-q", str(self.origin), str(self.clone))
        for args in (("config", "user.email", "t@t"), ("config", "user.name", "t")):
            git(self.clone, *args)
        git(self.clone, "checkout", "-q", "-b", "feat/x")
        # The PR's change lands on origin/main (the squash-merge) from elsewhere.
        (seed / "config.yaml").write_text("new\n")
        git(seed, "commit", "-q", "-am", "merged change")
        git(seed, "push", "-q", str(self.origin), "main")


class SyncCheckoutTests(GitRepoTestCase):
    def test_moves_feature_branch_checkout_to_merged_main(self):
        self.assertIsNone(prm.sync_checkout(str(self.clone)))
        self.assertEqual((self.clone / "config.yaml").read_text(), "new\n")

    def test_refuses_uncommitted_tracked_changes(self):
        (self.clone / "config.yaml").write_text("local edit\n")
        reason = prm.sync_checkout(str(self.clone))
        self.assertIn("uncommitted changes", reason)
        self.assertEqual((self.clone / "config.yaml").read_text(), "local edit\n")

    def test_untracked_files_do_not_block(self):
        (self.clone / "build.bin").write_text("x")
        self.assertIsNone(prm.sync_checkout(str(self.clone)))


class RunPostMergeTests(GitRepoTestCase):
    def run_post_merge(self, body, author="bot"):
        """Run run_post_merge with gh mocked. Returns (comment body or None, log)."""
        comments = []

        def fake_run(cmd, cfg, cwd=None):
            if cmd[:3] == ["gh", "pr", "view"]:
                return json.dumps({"body": body, "author": {"login": author}})
            if cmd[:2] == ["gh", "api"] and cmd[2].endswith("/comments"):
                comments.append(cmd[-1][len("body="):])
                return ""
            raise AssertionError(f"unexpected command {cmd}")

        out = io.StringIO()
        with mock.patch.object(prm, "run", side_effect=fake_run), \
             mock.patch.object(prm, "get_repo_nwo", return_value="owner/infra"), \
             mock.patch.dict(os.environ, {"GH_TOKEN": "secret-bot-token"}), \
             redirect_stdout(out):
            prm.run_post_merge(str(self.clone), 60, CFG)
        return (comments[0] if comments else None), out.getvalue()

    def test_runs_steps_against_merged_files_and_reports(self):
        body = ("## Post-merge\n"
                "- run: `cp config.yaml deployed.yaml`\n"
                "- run: `echo token=${GH_TOKEN:-unset}`\n")
        comment, _ = self.run_post_merge(body)
        self.assertEqual((self.clone / "deployed.yaml").read_text(), "new\n")
        self.assertTrue(comment.startswith(prm.POST_MERGE_MARKER))
        self.assertIn("✅ done", comment)
        self.assertIn("token=unset", comment)
        self.assertNotIn("secret-bot-token", comment)

    def test_stops_at_first_failure(self):
        body = ("## Post-merge\n"
                "- run: `echo boom >&2; exit 3`\n"
                "- run: `touch should-not-exist`\n")
        comment, out = self.run_post_merge(body)
        self.assertFalse((self.clone / "should-not-exist").exists())
        self.assertIn("❌ failed", comment)
        self.assertIn("exit 3", comment)
        self.assertIn("boom", comment)
        self.assertIn("⏸️ run `touch should-not-exist`", comment)
        self.assertIn("post-merge FAILED", out)

    def test_dirty_checkout_runs_nothing(self):
        (self.clone / "config.yaml").write_text("local edit\n")
        comment, _ = self.run_post_merge("## Post-merge\n- run: `touch ran`\n")
        self.assertFalse((self.clone / "ran").exists())
        self.assertIn("uncommitted changes", comment)
        self.assertIn("❌ failed", comment)

    def test_manual_steps_are_listed_not_run(self):
        comment, _ = self.run_post_merge("## Post-merge\n- manual: rename the device\n")
        self.assertIn("⏸️ manual: rename the device", comment)
        self.assertIn("✅ done", comment)

    def test_no_steps_posts_nothing(self):
        comment, out = self.run_post_merge(CASE_A_BODY)
        self.assertIsNone(comment)
        self.assertIn("post-merge: no steps", out)

    def test_other_authors_are_skipped(self):
        comment, out = self.run_post_merge("## Post-merge\n- run: `touch ran`\n",
                                           author="someone-else")
        self.assertIsNone(comment)
        self.assertFalse((self.clone / "ran").exists())
        self.assertIn("not the bot or owner", out)


class MergeTriggersPostMergeTests(PrMonitorTestCase):
    def test_post_merge_runs_after_successful_merge_only(self):
        self.write_state([{"repo": REPO, "pr": 7}])
        prs = json.dumps([{"number": 7, "headRefName": "feat/x", "author": {"login": "bot"}}])
        for merged in (True, False):
            with self.subTest(merged=merged), \
                 mock.patch.object(prm, "has_unresolved_comments", return_value=False), \
                 mock.patch.object(prm, "has_unresponded_conversation_comments", return_value=False), \
                 mock.patch.object(prm, "is_approved", return_value=True), \
                 mock.patch.object(prm, "squash_merge", return_value=merged), \
                 mock.patch.object(prm, "run_post_merge") as post_merge:
                self.write_state([{"repo": REPO, "pr": 7}])
                self.run_main([REPO], lambda cmd, cfg, cwd=None: prs)
                if merged:
                    post_merge.assert_called_once_with(REPO, 7, CFG)
                else:
                    post_merge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
