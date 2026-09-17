"""The commit gate checks index contents without disturbing concurrent working-tree edits."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("failing_tool", ["", "cargo", "uvx", "ruff"])
@pytest.mark.parametrize("alternate_index", [False, True])
def test_hook_checks_staged_snapshot_and_preserves_worktree(
    tmp_path, failing_tool, alternate_index
):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    env = dict(os.environ)
    if alternate_index:
        env["GIT_INDEX_FILE"] = str(tmp_path / "alternate-index")
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "marker").write_text("dependencies\n")
    tracked = repo / "partly_staged.py"
    tracked.write_text("staged content\n")
    subprocess.run(["git", "add", "partly_staged.py"], cwd=repo, env=env, check=True)
    tracked.write_text("unstaged content\n")
    untracked = repo / "untracked.py"
    untracked.write_text("untracked content\n")
    index_before = subprocess.check_output(["git", "ls-files", "--stage"], cwd=repo, env=env)

    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    shutil.copyfile(Path(__file__).parents[1] / ".githooks/pre-commit", hook)
    hook.chmod(0o755)
    commands = tmp_path / "bin"
    commands.mkdir()
    log = tmp_path / "calls"
    snapshot_log = tmp_path / "snapshot-path"
    # The commands are the external boundary: assert precisely which files they can see.
    for tool in ("cargo", "uvx", "ruff"):
        command = commands / tool
        command.write_text(
            "#!/bin/sh\nset -eu\n"
            'test "$(cat partly_staged.py)" = "staged content"\n'
            "test ! -e untracked.py\n"
            'test "$PWD" != "$ORIGINAL_REPO"\n'
            'test "$(cat .venv/marker)" = "dependencies"\n'
            'printf "%s" "$PWD" > "$SNAPSHOT_LOG"\n'
            f'echo "{tool} $*" >> "$CALL_LOG"\n'
            f'test "$FAILING_TOOL" != "{tool}"\n'
        )
        command.chmod(0o755)
    result = subprocess.run(
        ["git", "-c", f"core.hooksPath={hooks}", "hook", "run", "pre-commit"],
        cwd=repo,
        env={
            **env,
            "PATH": f"{commands}:{os.environ['PATH']}",
            "ORIGINAL_REPO": str(repo),
            "CALL_LOG": str(log),
            "SNAPSHOT_LOG": str(snapshot_log),
            "FAILING_TOOL": failing_tool,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (not failing_tool), result.stderr
    assert log.read_text().splitlines() == [
        "cargo check",
        "uvx ty check",
        "ruff check",
        "ruff format --check",
    ]
    assert tracked.read_text() == "unstaged content\n"
    assert untracked.read_text() == "untracked content\n"
    assert (
        subprocess.check_output(["git", "ls-files", "--stage"], cwd=repo, env=env) == index_before
    )
    assert not Path(snapshot_log.read_text()).exists()
