"""CLI regression: abbreviated IDs raised KeyError instead of resolving stored runs."""

import json
import sys

import pytest
from triplum.bench.cli import app
from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.runner import run_benchmark
from triplum.bench.runstore import RunStore
from typer.testing import CliRunner


@pytest.fixture
def runs(tmp_path):
    path = tmp_path / "runs.db"
    cfg = RunConfig(
        dataset="musique",
        n=1,
        fixture=True,
        pipeline=PipelineConfig(name="closed_book", reader=LLMConfig(kind="fake")),
        cache_root=str(tmp_path / "cache"),
        runstore_path=str(path),
    )
    rid = run_benchmark(cfg)
    rs = RunStore(path)
    # Predictable IDs expose prefix collisions without random test failures.
    rs.conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("runs", "run_questions", "events", "run_artifacts", "run_prices"):
        rs.conn.execute(f"UPDATE {table} SET run_id = ? WHERE run_id = ?", ("43a111111111", rid))
    row = rs.run("43a111111111")
    assert row is not None
    row["run_id"] = "43a222222222"
    row["identity_hash"] = "other-identity"
    row["reader_model"] = "other-reader"
    rs.conn.execute(
        f"INSERT INTO runs ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
        list(row.values()),
    )
    question = rs.questions("43a111111111").row(0, named=True)
    question.pop("run_id")
    question["question_id"] = "other-question"
    rs.add_question("43a222222222", question)
    rs.close()
    return str(path)


def invoke(args, runs, **kwargs):
    return CliRunner().invoke(app, ["bench", *args, "--runstore", runs], **kwargs)


@pytest.mark.parametrize("command", ["show", "inspect", "tail"])
def test_unique_prefix(command, runs):
    result = invoke([command, "43a1"], runs)
    assert result.exit_code == 0, result.output
    assert "43a111111111" in result.stdout


@pytest.mark.parametrize("command", ["show", "inspect", "rerun", "tail", "diff"])
def test_ambiguous_noninteractive_lists_candidates(command, runs):
    result = invoke([command, "43a"], runs)
    assert result.exit_code == 2, result.output
    assert "43a111111111" in result.output and "43a222222222" in result.output
    assert "Traceback" not in result.output


def test_interactive_omission_and_clean_json(runs, monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    result = invoke(["inspect", "--json"], runs, input="1\n")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["identity"]["run_id"] == "43a111111111"
    assert "closed_book" in result.stderr


def test_interactive_retry_and_cancel(runs, monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    result = invoke(["show", "43a"], runs, input="99\nq\n")
    assert result.exit_code == 1, result.output
    assert "Aborted" in result.output
    assert not result.stdout


def test_no_input_disables_terminal_prompt(runs, monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    result = CliRunner().invoke(app, ["--no-input", "bench", "show", "43a", "--runstore", runs])
    assert result.exit_code == 2, result.output
    assert "43a111111111" in result.stderr


def test_diff_resolves_both_ids(runs):
    result = invoke(["diff", "43a1", "43a2"], runs)
    assert result.exit_code == 0, result.output
    assert '"reader_model": ["fake-1", "other-reader"]' in result.stdout


def test_unknown_question_is_error(runs):
    result = invoke(["inspect", "43a1", "--question", "zzzzzzzzzz"], runs)
    assert result.exit_code == 2, result.output
    assert "question" in result.output.lower()


def test_command_prefix_and_typo(monkeypatch, tmp_path):
    monkeypatch.setenv("TRIPLUM_CACHE", str(tmp_path))
    result = CliRunner().invoke(app, ["ben", "rep"])
    assert result.exit_code == 0, result.output
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    result = CliRunner().invoke(app, ["bench", "reprt"], input="1\n")
    assert result.exit_code == 0, result.output
    assert "report" in result.stderr


def test_finite_choices_reach_canonical_config(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "run",
            "--pipeline",
            "CLOSED",
            "--dataset",
            "musique",
            "--reader",
            "fak",
            "--embedder",
            "fak",
            "--fixture",
            "--n",
            "1",
            "--cache-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    rs = RunStore(tmp_path / "runs.db")
    row = rs.runs().row(0, named=True)
    assert (row["dataset"], row["pipeline"]) == ("musique", "closed_book")
    rs.close()


def test_missing_store_and_unknown_id_are_usage_errors(tmp_path):
    for args in (["inspect"], ["inspect", "zzzz"]):
        result = invoke(args, str(tmp_path / "runs.db"))
        assert result.exit_code == 2, result.output
        assert "no" in result.output.lower() and "run" in result.output.lower()


def test_terminal_detection(monkeypatch):
    from triplum.bench.selection import is_interactive

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    assert not is_interactive()
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    assert is_interactive()


def test_exact_wins_over_prefix(monkeypatch):
    from triplum.bench.selection import resolve

    assert resolve("run", ["run", "runner"], "command") == "run"
    assert resolve("MUS", ["musique", "hotpotqa"], "dataset") == "musique"


def test_question_prefix_stays_scoped(runs):
    rs = RunStore(runs)
    qid = rs.questions("43a111111111")["question_id"][0]
    rs.close()
    result = invoke(["inspect", "43a1", "--question", qid[:5], "--json"], runs)
    assert result.exit_code == 0, result.output
    assert [q["question_id"] for q in json.loads(result.stdout)["questions"]] == [qid]
    other = invoke(["inspect", "43a2", "--question", qid], runs)
    assert other.exit_code == 2


def test_rerun_prefix_reuses_canonical_run(runs):
    result = invoke(["rerun", "43a1"], runs)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("reused 43a111111111")


def test_single_typo_match_is_accepted_without_prompt(runs):
    result = invoke(["show", "43a111111112", "--no-input"], runs)
    assert result.exit_code == 0, result.output
    assert "Using run: 43a111111111" in result.stderr
    assert json.loads(result.stdout)["identity"]["run_id"] == "43a111111111"


def test_missing_required_choices_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    result = CliRunner().invoke(
        app,
        ["bench", "run", "--fixture", "--n", "1", "--cache-root", str(tmp_path)],
        input="1\n2\n",
    )
    assert result.exit_code == 0, result.output
    rs = RunStore(tmp_path / "runs.db")
    row = rs.runs().row(0, named=True)
    assert (row["pipeline"], row["dataset"]) == ("closed_book", "musique")
    rs.close()


def test_help_never_prompts(monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    for args in (["--help"], ["ben", "run", "--help"], ["bench", "inspect", "--help"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.stdout
        assert "Select" not in result.stderr


@pytest.mark.parametrize("position", ["root", "group", "command"])
def test_no_input_at_each_level(position, runs, monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    args = ["bench", "show", "43a", "--runstore", runs]
    args.insert({"root": 0, "group": 1, "command": len(args)}[position], "--no-input")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.output
    assert "43a111111111" in result.stderr
    assert "Select a number" not in result.output


def test_lookup_missing_store_does_not_create_it(tmp_path):
    path = tmp_path / "absent" / "runs.db"
    result = invoke(["inspect", "43a"], str(path))
    assert result.exit_code == 2
    assert not path.parent.exists()


def test_noninteractive_command_typo_resolves(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPLUM_CACHE", str(tmp_path))
    result = CliRunner().invoke(app, ["bench", "reoprt"])
    assert result.exit_code == 0, result.output
    assert "Using command: report" in result.stderr


def test_adapter_suffix_preserved_and_missing_model_rejected():
    import typer
    from triplum.bench.selection import adapter

    model = "Vendor/MixedCase-Model:revision"
    assert adapter("ST:" + model, ["fake", "st", "openai"], "embedder", None) == "st:" + model
    for value in ["st", "st:", "fake:wrong"]:
        with pytest.raises(typer.BadParameter):
            adapter(value, ["fake", "st", "openai"], "embedder", None)


def test_fetch_dataset_prefix_default_and_all(monkeypatch, tmp_path):
    from triplum.eval.datasets import base, registry

    def _never(paths, n) -> base.Frames:
        raise AssertionError("parser must not run")

    seen = []

    def fetch(name, root=None):
        seen.append(name)
        return {"q": tmp_path / "questions"}

    monkeypatch.setattr(registry, "fetch", fetch)  # network boundary
    big = base.Spec(
        "big-test",
        "test",
        (base.File("u", "b", "0" * 64, base.LARGE_BYTES + 1),),
        "none",
        _never,
    )
    monkeypatch.setitem(registry.SPECS, big.name, big)
    result = CliRunner().invoke(app, ["data", "fetch", "--dataset", "moreh"])
    assert result.exit_code == 0, result.output
    assert seen == ["morehopqa"]
    seen.clear()
    result = CliRunner().invoke(app, ["data", "fetch"])
    assert result.exit_code == 0, result.output
    assert seen == ["hotpotqa", "musique", "twowiki"]
    seen.clear()
    result = CliRunner().invoke(app, ["data", "fetch", "--dataset", "ALL"])
    assert result.exit_code == 0, result.output
    assert seen == [name for name in registry.names() if not registry.get(name).large]
    assert "big-test: skipped" in result.output and "tempo: skipped" in result.output


def test_single_substring_match_is_accepted():
    from triplum.bench.selection import resolve

    assert resolve("book", ["closed_book", "oracle"], "pipeline") == "closed_book"


def test_diff_missing_second_id_lists_choices(runs):
    result = invoke(["diff", "43a1"], runs)
    assert result.exit_code == 2
    assert "43a111111111" in result.stderr and "43a222222222" in result.stderr


def test_no_input_suppresses_misspelled_command_prompt(monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    result = CliRunner().invoke(app, ["bench", "runn", "--no-input"])
    assert result.exit_code == 2
    assert "run" in result.stderr and "rerun" in result.stderr
    assert "Select a number" not in result.stderr


def test_no_input_does_not_leak_between_invocations(runs, monkeypatch):
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    assert invoke(["show", "43a", "--no-input"], runs).exit_code == 2
    result = invoke(["show", "43a"], runs, input="2\n")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["identity"]["run_id"] == "43a222222222"


def test_unknown_id_in_populated_store(runs):
    result = invoke(["inspect", "zzzzzzzzzzzz"], runs)
    assert result.exit_code == 2
    assert "No run matches" in result.stderr
    assert "43a111111111" in result.stderr


def test_empty_store_has_no_choices(tmp_path):
    path = tmp_path / "runs.db"
    RunStore(path).close()
    result = invoke(["inspect"], str(path))
    assert result.exit_code == 2
    assert "No run choices available" in result.stderr


def test_omitted_question_shows_every_question(runs):
    rs = RunStore(runs)
    row = rs.questions("43a111111111").row(0, named=True)
    first = row["question_id"]
    row.pop("run_id")
    row["question_id"] = "second-question"
    rs.add_question("43a111111111", row)
    rs.close()
    result = invoke(["inspect", "43a1", "--json"], runs)
    assert result.exit_code == 0, result.output
    assert {q["question_id"] for q in json.loads(result.stdout)["questions"]} == {
        first,
        "second-question",
    }


def test_sweep_finite_choices_are_canonical(tmp_path):
    specs = tmp_path / "embedders.json"
    specs.write_text('[{"kind": "fake", "dims": 8}]')
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "sweep",
            "--embedders",
            str(specs),
            "--dataset",
            "musique",
            "--reader",
            "fak",
            "--judge",
            "fak",
            "--reranker",
            "fak",
            "--fixture",
            "--n",
            "1",
            "--cache-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    rs = RunStore(tmp_path / "runs.db")
    row = rs.runs().row(0, named=True)
    rs.close()
    assert (row["dataset"], row["pipeline"], row["reader_model"]) == ("musique", "dense", "fake-1")


def test_report_accepts_no_input(tmp_path):
    result = invoke(["report", "--no-input"], str(tmp_path / "runs.db"))
    assert result.exit_code == 0, result.output


def test_multiple_typo_matches_still_require_a_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPLUM_CACHE", str(tmp_path))
    args = [
        "bench",
        "runn",
        "--pipeline",
        "closed",
        "--dataset",
        "musique",
        "--fixture",
        "--n",
        "1",
        "--cache-root",
        str(tmp_path),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "run" in result.stderr and "rerun" in result.stderr
    monkeypatch.setattr("triplum.bench.selection.is_interactive", lambda: True)
    chosen = CliRunner().invoke(app, args, input="1\n")
    assert chosen.exit_code == 0, chosen.output
    assert "Select a number" in chosen.stderr
    assert "pipeline=closed_book" in chosen.stdout
