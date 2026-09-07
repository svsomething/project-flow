"""
claude_runner — hardened, fail-loud wrapper around the Claude CLI, shared by
`project-monitor` and `pr-monitor`.

Both monitors used to call `subprocess.run(...)` and discard the result, so a
total failure (expired credentials, hung process) logged the same line as a
success and retried silently every minute. This module makes every failure
visible in three ways:

  1. Every non-OK outcome logs a line starting with `ERROR:` — greppable, and
     visually distinct from the routine `  Invoking Claude`.
  2. Credential failures trip a circuit breaker (`~/.claude/claude-auth-state.json`)
     so the monitors stop burning cycles on invocations that cannot succeed.
     One invocation every AUTH_RETRY_INTERVAL is let through as a live probe;
     success clears the breaker and logs RECOVERED.
  3. On the first credential failure for a card, the bot comments on the issue
     or PR asking for re-authentication. The bot's GH_TOKEN is entirely separate
     from Claude's credentials, so this still works when Claude auth is dead.

Auth detection does not rely on the exit code alone: it matches the auth
signature in the captured output *and* treats a non-zero exit as failure, so it
fires whether the CLI exits 1, exits 0, or hangs past the timeout.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Outcome statuses returned by run_claude()
OK          = "OK"
AUTH_FAILED = "AUTH_FAILED"
FAILED      = "FAILED"
TIMEOUT     = "TIMEOUT"
SKIPPED     = "SKIPPED"   # breaker open — Claude was never invoked

# Kill a hung invocation rather than letting it hold the monitor's PID lock
# indefinitely and wedge all board processing.
TIMEOUT_SECONDS = 1800

# How long the breaker stays closed before letting one probe invocation through.
AUTH_RETRY_INTERVAL = 900

AUTH_STATE_FILE = Path.home() / ".claude" / "claude-auth-state.json"

CLAUDE_BIN = Path(os.environ.get(
    "CLAUDE_BIN", Path.home() / ".npm-global" / "bin" / "claude"))

ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep"

# Heuristic: the first entry is the exact string from the 2026-06-22 incident,
# the rest are plausible variants. If the CLI reworks its wording a future auth
# failure falls through to the generic FAILED path — still logged as ERROR, still
# no silent retry loop, just without the auth-specific comment.
AUTH_SIGNATURES = (
    "Failed to authenticate",
    "Invalid authentication credentials",
    "Invalid API key",
    "OAuth token has expired",
    "Please run /login",
)

ALERT_HEADING  = "## ⚠️ Claude authentication required"
RESUME_HEADING = "## ✅ Claude authentication restored"

# First-line sentinels, matching the `pf:` markers project-monitor uses for its
# in-flight guards. These comments are bot comments like any other, so the board
# guards have to be able to tell them apart from a plan — matching a sentinel is
# structural, where matching the heading text breaks the moment the wording
# changes. Both headings stay recognised for comments posted before this.
ALERT_SENTINEL  = "<!-- pf:alert -->"
RESUME_SENTINEL = "<!-- pf:alert-cleared -->"


def _now():
    return datetime.now(timezone.utc)


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_log(msg):
    print(f"[{_ts(_now())}] {msg}", flush=True)


# ---------------------------------------------------------------- detection

def detect_auth_failure(text):
    """True if captured CLI output contains a known credential-failure signature."""
    if not text:
        return False
    lowered = text.lower()
    return any(sig.lower() in lowered for sig in AUTH_SIGNATURES)


def auth_error_excerpt(text, max_lines=5):
    """Return the matching lines from the captured output, for the alert body."""
    if not text:
        return ""
    matched = [line.strip() for line in text.splitlines()
               if detect_auth_failure(line)]
    if not matched:
        matched = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(matched[:max_lines])


# ------------------------------------------------------------ breaker state

def load_auth_state():
    """Return the breaker state dict, or None when credentials are believed good."""
    try:
        return json.loads(AUTH_STATE_FILE.read_text())
    except Exception:
        return None


def _save_auth_state(state):
    AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_STATE_FILE.write_text(json.dumps(state, indent=2))


def clear_auth_state():
    AUTH_STATE_FILE.unlink(missing_ok=True)


def breaker_status(now=None):
    """Return (should_skip, state).

    should_skip is True while the breaker is open and the retry interval has not
    yet elapsed. Once it has, one invocation is let through as a live probe.
    """
    state = load_auth_state()
    if not state:
        return False, None
    now = now or _now()
    try:
        last = datetime.fromisoformat(state["last_attempt"])
    except Exception:
        return False, state
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last < timedelta(seconds=AUTH_RETRY_INTERVAL), state


def record_auth_failure(message, now=None):
    """Open (or refresh) the breaker. Returns True if this is a newly opened breaker.

    The outage start time (`failed_at`) is preserved across repeated failures;
    only `last_attempt` moves, so the backoff restarts but the reported "broken
    since" timestamp stays honest.
    """
    now   = now or _now()
    state = load_auth_state()
    is_new = state is None
    if is_new:
        state = {"failed_at": _ts(now), "notified": []}
    state["last_attempt"] = _ts(now)
    state["message"] = message
    state.setdefault("notified", [])
    _save_auth_state(state)
    return is_new


def record_notified(target):
    """Mark a card as alerted, so the outage produces exactly one comment on it."""
    state = load_auth_state()
    if state is None:
        return
    state.setdefault("notified", [])
    if target not in state["notified"]:
        state["notified"].append(target)
        _save_auth_state(state)


def record_probe_attempt(now=None):
    """Note that a probe was let through, so the next one waits a full interval."""
    state = load_auth_state()
    if state:
        state["last_attempt"] = _ts(now or _now())
        _save_auth_state(state)


# ------------------------------------------------------------ notification

def _post_comment(target, body, env):
    """Comment on an issue or PR. The issues endpoint serves both."""
    repo   = target["repo"]
    number = target["number"]
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"],
        capture_output=True, text=True, env=env,
    )
    return result.returncode == 0, result.stderr.strip()


def _already_alerted(target, env, bot_login):
    """True if the bot has already posted an alert on this issue/PR.

    Matches only when the sentinel (or, for older comments, the heading) *starts*
    the comment — a plan or summary that merely quotes it must not suppress a
    real alert.
    """
    if not bot_login:
        return False
    repo   = target["repo"]
    number = target["number"]
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{number}/comments",
         "--paginate", "--jq", "[.[] | {author: .user.login, body}]"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        return False
    try:
        comments = json.loads(result.stdout)
    except Exception:
        return False
    return any(c.get("author") == bot_login
               and (c.get("body") or "").lstrip().startswith(
                   (ALERT_SENTINEL, ALERT_HEADING))
               for c in comments)


def notify_auth_failure(target, excerpt, env, bot_login, log=_default_log):
    """Post the re-authentication request once per card."""
    state = load_auth_state() or {}
    if target in state.get("notified", []):
        return False
    if _already_alerted(target, env, bot_login):
        return False

    minutes = AUTH_RETRY_INTERVAL // 60
    body = (
        f"{ALERT_SENTINEL}\n"
        f"{ALERT_HEADING}\n\n"
        "I could not act on this card — the Claude CLI failed to authenticate "
        "on the host.\n\n"
        f"```\n{excerpt}\n```\n\n"
        "Run `claude` on the host and re-authenticate. This card stays in its "
        f"current column and I will pick it up automatically within ~{minutes} "
        "minutes of credentials being restored. No action needed on this issue."
    )
    posted, err = _post_comment(target, body, env)
    if posted:
        record_notified(target)
        log(f"  Posted auth alert on {target['repo']}#{target['number']}")
    else:
        log(f"  ERROR: could not post auth alert on "
            f"{target['repo']}#{target['number']}: {err}")
    return posted


def notify_recovery(targets, env, log=_default_log):
    """Post the resume reply on every card that was alerted during the outage."""
    body = (
        f"{RESUME_SENTINEL}\n"
        f"{RESUME_HEADING}\n\n"
        "Claude authenticated successfully again — resuming work on this card."
    )
    for target in targets:
        posted, err = _post_comment(target, body, env)
        if not posted:
            log(f"  ERROR: could not post recovery notice on "
                f"{target['repo']}#{target['number']}: {err}")


# ------------------------------------------------------------------ runner

def run_claude(prompt, env, cwd=None, target=None, bot_login=None,
               log=_default_log, timeout=None, claude_bin=None, model=None):
    """Invoke Claude non-interactively. Returns one of the status constants.

    `target` is an optional {"repo": "owner/name", "number": N} dict identifying
    the issue or PR to comment on when credentials fail.

    `model` is an optional CLI model alias ("opus", "sonnet", "haiku"). When
    set, it is passed through as `--model`; when None the CLI's own default
    applies, unchanged from before this parameter existed.
    """
    timeout = timeout or TIMEOUT_SECONDS
    binary  = str(claude_bin or CLAUDE_BIN)

    should_skip, state = breaker_status()
    if should_skip:
        log(f"  SKIP: Claude auth broken since {state.get('failed_at')}")
        return SKIPPED
    probing = state is not None
    if probing:
        record_probe_attempt()

    cmd = [binary, "-p", prompt, "--allowedTools", ALLOWED_TOOLS]
    if model:
        cmd += ["--model", model]
    log("  Invoking Claude" + (f" (cwd={Path(cwd).name})" if cwd else "")
        + (f" (model={model})" if model else ""))

    timed_out = False
    try:
        result   = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                                  capture_output=True, timeout=timeout)
        output   = (result.stdout or "") + (result.stderr or "")
        returncode = result.returncode
    except subprocess.TimeoutExpired as e:
        timed_out  = True
        returncode = None
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        output = out + err
    except FileNotFoundError:
        log(f"  ERROR: Claude binary not found at {binary}")
        return FAILED

    # Keep everything the log showed before, but attributable and indented.
    for line in output.splitlines():
        log(f"  claude| {line}")

    if detect_auth_failure(output):
        excerpt = auth_error_excerpt(output)
        first   = excerpt.splitlines()[0] if excerpt else "credential failure detected"
        log(f"  ERROR: Claude authentication failed — {first}")
        record_auth_failure(excerpt)
        if target:
            notify_auth_failure(target, excerpt, env, bot_login, log)
        return AUTH_FAILED

    if timed_out:
        log(f"  ERROR: Claude timed out after {timeout}s and was killed")
        return TIMEOUT

    if returncode != 0:
        log(f"  ERROR: Claude exited with code {returncode}")
        return FAILED

    if probing:
        log("  RECOVERED: Claude authentication restored")
        recovered_state = load_auth_state() or {}
        clear_auth_state()
        notify_recovery(recovered_state.get("notified", []), env, log)

    return OK
