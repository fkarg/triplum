"""`triplum datasets` commands and the admin functions they wrap, over a temporary catalogue."""

import hashlib
import io
import json
import ssl
import urllib.error
from pathlib import Path

import pytest

from triplum import cli
from triplum.datasets import admin, files
from triplum.datasets.admin import dataset_status, remove_dataset, verify_dataset
from triplum.datasets.files import DatasetEntry, PinnedFile


@pytest.fixture
def entry(tmp_path: Path, monkeypatch) -> DatasetEntry:
    """A two-file dataset served from file:// URLs, the only catalogue entry."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    remote = tmp_path / "remote"
    remote.mkdir()
    pinned = []
    for name, data in (("a.json", b"[1]"), ("b.json", b"[22]")):
        (remote / name).write_bytes(data)
        pinned.append(
            PinnedFile(
                name=name,
                url=(remote / name).as_uri(),
                sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data),
            )
        )
    demo = DatasetEntry(
        name="demo", files=pinned, licence="CC BY 4.0", commercial_reuse="With attribution"
    )
    monkeypatch.setattr(cli, "CATALOGUE", {"demo": demo})
    return demo


def _folder(tmp_path: Path) -> Path:
    return tmp_path / "xdg" / "triplum" / "datasets" / "demo"


def _run(capsys, *args: str) -> tuple[int, str, str]:
    try:
        code = cli.main(list(args))
    except SystemExit as exit:
        code = exit.code if isinstance(exit.code, int) else 1
    out, err = capsys.readouterr()
    return code, out, err


def test_status_counts_present_files_without_hashing(entry, tmp_path, monkeypatch):
    def no_hashing(path):
        raise AssertionError("status must not hash")

    monkeypatch.setattr(admin, "sha256_of", no_hashing)
    assert dataset_status(entry).status == "missing"
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"corrupt but present")
    status = dataset_status(entry)
    assert (status.status, [f.bytes for f in status.files]) == ("partial", [19, None])
    (folder / "b.json").write_bytes(b"[22]")
    assert dataset_status(entry).status == "present"


@pytest.mark.parametrize("locked", ["file", "folder"])
def test_unreadable_paths_are_errors_not_present_or_missing(entry, tmp_path, locked):
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"[1]")
    target = folder / "a.json" if locked == "file" else folder
    target.chmod(0)
    try:
        with pytest.raises(PermissionError):
            dataset_status(entry)
        assert "Permission denied" in verify_dataset(entry)[0]
    finally:
        target.chmod(0o700)


def test_status_and_remove_reject_a_directory_in_place_of_a_file(entry, tmp_path):
    (_folder(tmp_path) / "a.json").mkdir(parents=True)
    with pytest.raises(ValueError, match="is not a file"):
        dataset_status(entry)
    with pytest.raises(ValueError, match="is not a file"):
        remove_dataset(entry)


def test_verify_reports_every_problem_and_repairs_nothing(entry, tmp_path):
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"[9]")
    problems = verify_dataset(entry)
    assert [p.split(": ")[1].split(" ")[0] for p in problems] == ["sha256", "missing"]
    assert (folder / "a.json").read_bytes() == b"[9]"
    assert not (folder / "b.json").exists()


def test_remove_deletes_declared_files_only(entry, tmp_path):
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"[1]")
    (folder / "notes.txt").write_text("mine")
    assert remove_dataset(entry) == 3
    assert [p.name for p in folder.iterdir()] == ["notes.txt"]
    (folder / "notes.txt").unlink()
    assert remove_dataset(entry) == 0
    assert not folder.exists()


def test_download_verify_list_remove_round_trip(entry, tmp_path, capsys):
    assert _run(capsys, "datasets", "download", "demo")[0] == 0
    code, out, _ = _run(capsys, "datasets", "list", "--json")
    [listed] = json.loads(out)
    assert (code, listed["status"], listed["folder"]) == (0, "present", str(_folder(tmp_path)))
    assert _run(capsys, "datasets", "verify", "demo")[1] == "demo: all files verified\n"
    code, out, _ = _run(capsys, "datasets", "remove", "demo", "--json")
    assert (code, json.loads(out)) == (0, {"dataset": "demo", "removed_bytes": 7})
    assert _run(capsys, "datasets", "list")[1] == (
        f"demo  missing  {_folder(tmp_path)}\n"
        "  a.json  missing, expected 3 bytes\n"
        "  b.json  missing, expected 4 bytes\n"
    )


def test_verify_fails_on_a_corrupt_file_and_download_refuses_to_replace_it(entry, tmp_path, capsys):
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"[9]")
    code, out, _ = _run(capsys, "datasets", "verify", "demo", "--json")
    assert (code, json.loads(out)["ok"]) == (1, False)
    code, _, err = _run(capsys, "datasets", "download", "demo")
    assert code == 2 and "remove it to download again" in err
    assert (folder / "a.json").read_bytes() == b"[9]"


def test_names_match_forgivingly_and_report_the_match(entry, capsys):
    code, out, err = _run(capsys, "data", "lic", "dem")
    assert code == 0
    assert out == "demo: CC BY 4.0\nCommercial reuse: With attribution\n"
    assert "matched 'datasets'" in err and "matched 'licence'" in err and "matched 'demo'" in err


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["datasets"], "choices: list, download, verify, remove, licence"),
        (["datasets", "verify"], "needs a dataset name; choices: demo"),
        (["datasets", "list", "demo"], "takes no dataset name"),
        (["datasets", "list", "--path", "x"], "apply only to cache commands"),
        (["cache", "stats", "demo"], "take no dataset name"),
    ],
)
def test_misused_commands_explain_themselves(entry, capsys, args, message):
    code, _, err = _run(capsys, *args)
    assert code == 2 and message in err and "Traceback" not in err


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("limit", "stdin", "extra", "removed"),
    [
        (7, None, [], True),  # exactly at the threshold: no question
        (6, None, [], False),  # above it without a terminal: refuses
        (6, None, ["--yes"], True),
        (6, "y\n", [], True),
        (6, "n\n", [], False),
        (6, "y\n", ["--no-input"], False),
    ],
    ids=["at-limit", "no-terminal", "yes", "answer-yes", "answer-no", "no-input"],
)
def test_removing_more_than_the_threshold_asks_first(
    entry, tmp_path, capsys, monkeypatch, limit, stdin, extra, removed
):
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"[1]")
    (folder / "b.json").write_bytes(b"[22]")  # 7 bytes in all
    monkeypatch.setattr(cli, "PROMPT_BYTES", limit)
    monkeypatch.setattr(cli.sys, "stdin", _Terminal(stdin) if stdin else io.StringIO())
    code, _, _ = _run(capsys, "datasets", "remove", "demo", *extra)
    assert (code == 0) == removed
    assert (_folder(tmp_path) / "a.json").exists() != removed


def test_the_real_catalogue_lists_hotpotqa_and_multihoprag():
    from triplum.datasets.catalogue import CATALOGUE

    assert list(CATALOGUE) == ["hotpotqa", "multihoprag"]
    for entry in CATALOGUE.values():
        assert entry.files and entry.licence and entry.commercial_reuse
        assert all(len(f.sha256) == 64 and f.bytes > 0 for f in entry.files)


def test_licence_json_and_tls_failures_explain_themselves(entry, capsys, monkeypatch):
    code, out, _ = _run(capsys, "datasets", "licence", "demo", "--json")
    assert (code, json.loads(out)) == (
        0,
        {"dataset": "demo", "licence": "CC BY 4.0", "commercial_reuse": "With attribution"},
    )

    def untrusted(url, timeout):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))

    monkeypatch.setattr(files.urllib.request, "urlopen", untrusted)
    code, _, err = _run(capsys, "datasets", "download", "demo")
    assert code == 2 and "Traceback" not in err
    assert "a.json failed" in err and "point SSL_CERT_FILE at your CA bundle" in err


def test_remove_needs_no_read_permission(entry, tmp_path):
    folder = _folder(tmp_path)
    folder.mkdir(parents=True)
    (folder / "a.json").write_bytes(b"[9]")
    (folder / "a.json").chmod(0)
    assert remove_dataset(entry) == 3
    assert not folder.exists()
