import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY = REPO_ROOT / "scripts" / "supersaiyan-dispatch-policy.sh"
CODEX_RUNNER = REPO_ROOT / "scripts" / "supersaiyan-codex-run.sh"
CURSOR_RUNNER = REPO_ROOT / "scripts" / "supersaiyan-cursor-run.sh"
CONFIG = REPO_ROOT / ".claude" / "supersaiyan" / "configs" / "ai-researcher.json"
CURSOR_CONFIG = REPO_ROOT / ".claude" / "supersaiyan" / "configs" / "ai-researcher-cursor.json"
WATCHER = REPO_ROOT / "scripts" / "watch-run.sh"
CURSOR_DOCS = REPO_ROOT / "docs" / "supersaiyan" / "cursor-runner.md"


def eligible_ready_issue(items: list[dict]) -> str:
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; strict_serial_ready_issue "$2"',
            "bash",
            str(POLICY),
            json.dumps({"items": items}),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def issue(number: int, status: str, *, assignees: list[str] | None = None) -> dict:
    return {
        "status": status,
        "content": {
            "type": "Issue",
            "number": number,
            "assignees": assignees or [],
        },
    }


def test_successor_waits_while_predecessor_is_in_qa() -> None:
    assert eligible_ready_issue([issue(2, "QA"), issue(3, "Ready")]) == ""


def test_successor_becomes_eligible_after_predecessor_is_done() -> None:
    assert eligible_ready_issue([issue(2, "Done"), issue(3, "Ready")]) == "3"


def test_lowest_active_task_controls_the_serial_chain() -> None:
    assert eligible_ready_issue([issue(5, "Ready"), issue(3, "Ready"), issue(4, "Ready")]) == "3"


def test_blocked_predecessor_stops_later_ready_tasks() -> None:
    assert eligible_ready_issue([issue(2, "Blocked"), issue(3, "Ready")]) == ""


def test_claimed_ready_task_is_not_eligible() -> None:
    assert eligible_ready_issue([issue(2, "Ready", assignees=["worker"])]) == ""


def _busy_wait_block(runner: str) -> str:
    # The event-driven busy-wait: local PID liveness only, no GitHub calls.
    # Bounded by two comments authored verbatim in both runner scripts, so
    # this extraction is stable across edits that don't touch that shape.
    start = runner.index("# At least one lane is busy.")
    end = runner.index("# Fully idle: nothing local left to react to.")
    return runner[start:end]


def test_runners_poll_locally_while_busy_and_forbid_worker_board_scans() -> None:
    for runner_path in (CODEX_RUNNER, CURSOR_RUNNER):
        runner = runner_path.read_text()

        # Board polling is event-driven, not timer-driven: no fixed tick.
        assert "TICK_SECONDS" not in runner
        assert "POLL_SECONDS" in runner
        assert "IDLE_RECHECK_SECONDS" in runner

        # While any lane is busy, the wait loop must be local-only -- a
        # regression here is exactly what caused the GraphQL exhaustion
        # incident this architecture replaces.
        busy_wait = _busy_wait_block(runner)
        assert "fetch_project_items" not in busy_wait
        assert "gh project item-list" not in busy_wait
        assert "kill -0" in busy_wait or "lane_idle" in busy_wait

        # The real pass (outside the busy-wait block) still fetches.
        assert "fetch_project_items" in runner

        # Idle-only recheck exists as the sole periodic fallback, and is not
        # itself reachable from the busy-wait block.
        assert 'sleep "$IDLE_RECHECK_SECONDS"' in runner
        assert "IDLE_RECHECK_SECONDS" not in busy_wait

        assert r"Do NOT run \`gh project item-list\`" in runner
        assert r"Do NOT run \`gh project field-list\`" in runner
        assert r"Do NOT run \`gh project view\`" in runner


def test_cursor_backend_is_configured_and_guarded() -> None:
    # Reads the Cursor-dedicated config, not the shared ai-researcher.json --
    # worker_backend on the shared file is mutable and gets flipped by whichever
    # tool ran last. The per-tool config files exist precisely so this kind of
    # assertion is stable regardless of which dispatcher a human ran most recently.
    config = json.loads(CURSOR_CONFIG.read_text())
    runner = CURSOR_RUNNER.read_text()

    assert CURSOR_RUNNER.is_file()
    assert config["worker_backend"] == "cursor-agent"
    assert config["cursor"]["model"]
    assert 'WORKER_BACKEND" != "cursor-agent"' in runner or (
        '"cursor-agent"' in runner and "worker_backend=${WORKER_BACKEND}" in runner
    )
    assert "require_cursor_subscription_auth" in runner
    assert "agent login" in runner
    assert "CURSOR_API_KEY is set" in runner
    assert "nohup agent" in runner
    assert "--force" in runner
    assert "--trust" in runner
    assert "cursor-logs" in runner
    assert "supersaiyan-codex-run" in runner  # mutual exclusion
    # "Not logged in" must be treated as unauthenticated (substring "logged in" trap).
    assert "not logged in" in runner


def test_cursor_runner_rejects_wrong_backend() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config_dir = root / ".claude" / "supersaiyan" / "configs"
        config_dir.mkdir(parents=True)
        config = json.loads(CONFIG.read_text())
        config["worker_backend"] = "codex-exec"
        (config_dir / "ai-researcher.json").write_text(json.dumps(config))
        script = root / "supersaiyan-cursor-run.sh"
        shutil.copy(CURSOR_RUNNER, script)
        script.chmod(0o755)
        policy = root / "supersaiyan-dispatch-policy.sh"
        shutil.copy(POLICY, policy)

        # Rewrite the sourced policy path to the temp copy.
        text = script.read_text()
        text = text.replace(
            '. "$(dirname "$0")/supersaiyan-dispatch-policy.sh"',
            f'. "{policy}"',
        )
        script.write_text(text)

        result = subprocess.run(
            ["bash", str(script), "ai-researcher"],
            check=False,
            capture_output=True,
            text=True,
            cwd=root,
            env={k: v for k, v in os.environ.items() if k != "CURSOR_API_KEY"},
        )
        assert result.returncode == 78, result.stderr + result.stdout
        assert "cursor-agent" in result.stderr


def test_cursor_docs_describe_subscription_auth() -> None:
    docs = CURSOR_DOCS.read_text()
    assert "agent login" in docs
    assert "CURSOR_API_KEY" in docs
    assert "subscription" in docs.lower()
    assert "CURSOR_MAX_PARALLEL=1" in docs


def test_dashboard_selects_logs_for_cursor_backend() -> None:
    watcher = WATCHER.read_text()

    assert 'REFRESH="${REFRESH:-600}"' in watcher
    assert "cursor-logs" in watcher
    assert "cursor-agent" in watcher
    assert "codex-logs" in watcher


def test_cached_card_can_only_be_dispatched_once_offline() -> None:
    with tempfile.TemporaryDirectory() as directory:
        marker_dir = Path(directory)
        command = (
            'source "$1"; '
            'offline_dispatch_available "$2" "$3" && '
            'mark_offline_dispatch "$2" "$3" && '
            '! offline_dispatch_available "$2" "$3"'
        )
        result = subprocess.run(
            ["bash", "-c", command, "bash", str(POLICY), str(marker_dir), "2"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
