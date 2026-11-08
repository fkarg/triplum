"""Inspect, verify and remove downloaded datasets; the `triplum datasets` commands wrap these."""

import errno
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from triplum.datasets.files import DatasetEntry, datasets_home, existing, sha256_of


@dataclass(frozen=True)
class FileStatus:
    name: str
    expected_bytes: int
    bytes: int | None  # None when the file is missing


@dataclass(frozen=True)
class DatasetStatus:
    name: str
    folder: Path
    status: Literal["missing", "partial", "present"]
    files: list[FileStatus]


def dataset_status(entry: DatasetEntry, root: Path | None = None) -> DatasetStatus:
    """Which of the entry's files are present, and their sizes. Neither downloads nor hashes.

    `present` means every file exists, not that its content is verified. A non-file or
    unreadable path raises.
    """
    folder = (datasets_home() if root is None else root) / entry.name
    files = []
    for file in entry.files:
        path = existing(folder / file.name)
        size = None if path is None else path.stat().st_size
        files.append(FileStatus(name=file.name, expected_bytes=file.bytes, bytes=size))
    found = sum(f.bytes is not None for f in files)
    status = "missing" if found == 0 else "present" if found == len(files) else "partial"
    return DatasetStatus(name=entry.name, folder=folder, status=status, files=files)


def verify_dataset(entry: DatasetEntry, root: Path | None = None) -> list[str]:
    """One problem per missing, unreadable or mismatched file; `[]` when all verify.

    Every file is checked; nothing is downloaded or repaired.
    """
    folder = (datasets_home() if root is None else root) / entry.name
    problems = []
    for file in entry.files:
        try:
            path = existing(folder / file.name)
            if path is None:
                problems.append(f"{folder / file.name}: missing")
            elif (actual := sha256_of(path)) != file.sha256:
                problems.append(f"{path}: sha256 {actual}, expected {file.sha256}")
        except (OSError, ValueError) as error:
            problems.append(f"{folder / file.name}: {error}")
    return problems


def remove_dataset(entry: DatasetEntry, root: Path | None = None) -> int:
    """Delete the entry's files, and its folder if then empty; return the bytes removed.

    Missing files are skipped. Other files in the folder stay. A download running at the same
    time may install files again afterwards.
    """
    folder = (datasets_home() if root is None else root) / entry.name
    removed = 0
    for file in entry.files:
        path = folder / file.name
        try:
            info = path.lstat()  # no read permission needed: a corrupt file must be removable
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{path} is not a file")
        removed += info.st_size
        path.unlink()
    try:
        folder.rmdir()
    except FileNotFoundError:
        pass
    except OSError as error:  # not empty: other files, or a download running at the same time
        if error.errno != errno.ENOTEMPTY:
            raise
    return removed
