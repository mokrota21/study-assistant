"""Check that this machine can actually run the harness.

    uv run python -m tests.doctor          # report
    uv run python -m tests.doctor --fix    # also repair what is safely repairable

Run this after cloning. It checks the things that fail *silently* — above all
the hook interpreter, because a hook that cannot start just exits quietly and
you get no block clock with no error anywhere.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = "--fix" in sys.argv

OK, WARN, FAIL = "ok  ", "warn", "FAIL"
results: list[tuple[str, str, str]] = []


def report(level: str, label: str, detail: str = "") -> None:
    results.append((level, label, detail))
    line = f"  {level}  {label}"
    print(line if not detail else f"{line}\n        {detail}")


def bare_path() -> str:
    """PATH with this virtualenv stripped out.

    `uv run` prepends .venv/Scripts (or .venv/bin) to PATH, but Claude Code
    launches hooks from your normal shell, which has no such entry. Resolving
    against the inherited PATH would report a working interpreter that the real
    hooks cannot see — a false pass on the one check that matters most here.
    """
    venv = os.environ.get("VIRTUAL_ENV")
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if venv:
        venv_norm = os.path.normcase(os.path.normpath(venv))
        entries = [
            e
            for e in entries
            if not os.path.normcase(os.path.normpath(e)).startswith(venv_norm)
        ]
    return os.pathsep.join(entries)


def which_outside_venv(command: str) -> str | None:
    return shutil.which(command, path=bare_path())


def hook_interpreter() -> str | None:
    """The interpreter name the hooks are configured to launch."""
    settings = REPO / ".claude" / "settings.json"
    if not settings.exists():
        return None
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for entries in (data.get("hooks") or {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                command = hook.get("command", "")
                match = re.match(r'^\s*"?([^"\s]+)"?\s', command)
                if match:
                    return match.group(1)
    return None


def set_hook_interpreter(new: str) -> None:
    settings = REPO / ".claude" / "settings.json"
    text = settings.read_text(encoding="utf-8")
    old = hook_interpreter()
    settings.write_text(text.replace(f'"command": "{old} ', f'"command": "{new} '), encoding="utf-8")


def check_tooling() -> None:
    print("\ntooling")
    uv = shutil.which("uv")
    if uv:
        version = subprocess.run([uv, "--version"], capture_output=True, text=True).stdout.strip()
        report(OK, f"uv found ({version})")
    else:
        report(FAIL, "uv not found on PATH", "Install from https://docs.astral.sh/uv/getting-started/installation/")

    claude = shutil.which("claude")
    if claude:
        report(OK, "claude CLI found")
    else:
        report(
            WARN,
            "claude CLI not on PATH",
            "Needed to actually use the harness. https://claude.com/claude-code",
        )


def check_dependencies() -> None:
    print("\npython environment")
    report(OK, f"running Python {platform.python_version()} ({sys.platform})")
    missing = []
    for module in ("mcp", "fsrs", "pydantic", "pydantic_settings"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        report(FAIL, f"missing packages: {', '.join(missing)}", "Run: uv sync")
    else:
        from importlib.metadata import PackageNotFoundError, version

        def ver(name: str) -> str:
            try:
                return version(name)
            except PackageNotFoundError:
                return "?"

        report(OK, f"dependencies installed (mcp {ver('mcp')}, fsrs {ver('fsrs')}, pydantic {ver('pydantic')})")


def check_paths() -> None:
    print("\nproject layout")
    from harness.config import get_settings

    settings = get_settings()
    if Path(settings.root) == REPO:
        report(OK, f"harness root resolves to {REPO}")
    else:
        report(FAIL, f"harness root is {settings.root}, expected {REPO}", "Unset HARNESS_ROOT, or set it to this folder.")

    try:
        probe = Path(settings.state_dir) / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        report(OK, "state/ is writable")
    except Exception as exc:
        report(FAIL, f"state/ is not writable: {exc}")

    for required in (".mcp.json", ".claude/settings.json", "CLAUDE.md", "config.json"):
        if (REPO / required).exists():
            report(OK, f"{required} present")
        else:
            report(FAIL, f"{required} is missing", "Re-clone, or restore it from git.")


def check_server() -> None:
    print("\nMCP server")
    config = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    entry = config["mcpServers"]["learning-harness"]
    command = [entry["command"], *entry["args"]]
    if not shutil.which(entry["command"]):
        report(FAIL, f"'{entry['command']}' from .mcp.json is not on PATH")
        return
    proc = subprocess.Popen(
        command, cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    handshake = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "doctor", "version": "0"},
            },
        }
    )
    try:
        out, err = proc.communicate(handshake + "\n", timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        report(FAIL, "MCP server did not respond within 90s")
        return
    if '"serverInfo"' in out or '"server_info"' in out or "learning-harness" in out:
        report(OK, "MCP server starts and completes the handshake")
    else:
        report(FAIL, "MCP server did not answer initialize", (err or out or "")[:300])


def check_hooks() -> None:
    print("\nClaude Code hooks (the part that fails silently)")
    interpreter = hook_interpreter()
    if not interpreter:
        report(FAIL, "could not read the hook command from .claude/settings.json")
        return

    resolved = which_outside_venv(interpreter)
    if not resolved:
        alternatives = [c for c in ("python3", "python", "py") if which_outside_venv(c)]
        detail = (
            f"Hooks are configured to run '{interpreter}', which is not on PATH. "
            "They will exit silently and you will get no block clock.\n        "
            + (
                f"Working alternatives here: {', '.join(alternatives)}. "
                + (
                    f"Re-run with --fix to switch to '{alternatives[0]}'."
                    if alternatives
                    else ""
                )
                if alternatives
                else "No Python interpreter found on PATH at all."
            )
        )
        if FIX and alternatives:
            set_hook_interpreter(alternatives[0])
            report(OK, f"hook interpreter switched from '{interpreter}' to '{alternatives[0]}'")
            interpreter, resolved = alternatives[0], which_outside_venv(alternatives[0])
        else:
            report(FAIL, f"hook interpreter '{interpreter}' not found", detail)
            return
    else:
        report(OK, f"hook interpreter '{interpreter}' resolves to {resolved}", "(checked against your shell PATH, not this virtualenv)")

    version = subprocess.run(
        [resolved, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if version and tuple(int(p) for p in version.split(".")[:2]) < (3, 7):
        report(FAIL, f"hook interpreter is Python {version}", "Hooks need 3.7+. Point them at a newer interpreter.")
        return
    report(OK, f"hook interpreter is Python {version} (stdlib only, no venv needed)")

    # End-to-end: a synthetic active block must produce a clock line.
    sandbox = Path(tempfile.mkdtemp(prefix="harness-doctor-"))
    (sandbox / "state").mkdir(parents=True)
    start = (datetime.now().astimezone() - timedelta(minutes=20)).isoformat(timespec="seconds")
    (sandbox / "state" / "block.json").write_text(
        json.dumps(
            {
                "active": True,
                "start": start,
                "duration_minutes": 50,
                "segment": "review",
                "subject": "doctor",
                "solo_mode": True,
            }
        ),
        encoding="utf-8",
    )
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(sandbox))
    proc = subprocess.run(
        [resolved, str(REPO / ".claude" / "hooks" / "block_status.py")],
        input=json.dumps({"hook_event_name": "UserPromptSubmit"}),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        report(FAIL, f"block_status hook exited {proc.returncode}", proc.stderr[:300])
    elif "Block 20/50min" in proc.stdout:
        report(OK, "block clock hook produces the expected context line")
    else:
        report(FAIL, "block clock hook ran but produced no clock line", (proc.stdout or "(no output)")[:300])

    if "SOLO MODE IS ACTIVE" in proc.stdout:
        report(OK, "solo-mode guardrail is injected")
    else:
        report(FAIL, "solo-mode guardrail was not injected", "This is the main pedagogical safeguard.")


def check_notifications() -> None:
    print("\ndesktop notifications")
    if sys.platform == "win32":
        report(OK, "Windows toast backend (tested)")
    elif sys.platform == "darwin":
        report(WARN, "macOS osascript backend (implemented, untested)", "Verify with: uv run python -c \"from harness.notify import notify; print(notify('test','hi'))\"")
    else:
        if shutil.which("notify-send"):
            report(WARN, "Linux notify-send backend (implemented, untested)")
        else:
            report(WARN, "notify-send not installed", "Block-end popups will not fire. Install libnotify-bin, or set notifications_enabled=false.")


def main() -> int:
    print(f"Learning Harness doctor\n{REPO}")
    check_tooling()
    check_dependencies()
    check_paths()
    check_server()
    check_hooks()
    check_notifications()

    failures = [r for r in results if r[0] == FAIL]
    warnings = [r for r in results if r[0] == WARN]
    print("\n" + "-" * 60)
    if failures:
        print(f"{len(failures)} problem(s) must be fixed before the harness will work:")
        for _, label, _ in failures:
            print(f"  - {label}")
        if not FIX:
            print("\nSome of these are auto-repairable: re-run with --fix")
        return 1
    print(f"Everything works. {len(warnings)} warning(s)." if warnings else "Everything works.")
    print("\nNext: run `claude` in this folder, then `/intake <subject>`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
