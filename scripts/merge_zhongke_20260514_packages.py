from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "\u56db\u8bca\u4eea\u6570\u636e\u6574\u7406"
ZHONGKE_ROOT = DATA_ROOT / "\u4e2d\u79d1\u56db\u8bca\u4eea"
TARGET_NAME = "2026.05.14(\u5168\u90e8)"
SOURCE_PREFIX = "2026.05.14(\u5168\u90e8)"


@dataclass
class MergeStats:
    temp_files_deleted: int = 0
    temp_files_delete_failed: int = 0
    dirs_created: int = 0
    files_copied: int = 0
    files_skipped_identical: int = 0
    files_renamed_conflict: int = 0


def safe_text(value: object) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")


def log(message: str, *, verbose: bool) -> None:
    if verbose:
        print(safe_text(message))


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_temp_file(path: Path) -> bool:
    return path.is_file() and path.name.startswith("._")


def discover_source_dirs() -> list[Path]:
    if not ZHONGKE_ROOT.exists():
        raise FileNotFoundError(f"Missing root: {ZHONGKE_ROOT}")
    target = ZHONGKE_ROOT / TARGET_NAME
    return sorted(
        path
        for path in ZHONGKE_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith(SOURCE_PREFIX)
        and path.resolve() != target.resolve()
    )


def cleanup_temp_files(paths: list[Path], *, apply: bool, stats: MergeStats, verbose: bool) -> None:
    for root in paths:
        if not root.exists():
            continue
        for temp_file in root.rglob("._*"):
            if not is_temp_file(temp_file):
                continue
            stats.temp_files_deleted += 1
            log(f"DELETE_TEMP {temp_file}", verbose=verbose)
            if apply:
                try:
                    os.chmod(temp_file, 0o666)
                except OSError:
                    pass
                subprocess.run(["attrib", "-H", "-S", "-R", str(temp_file)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    temp_file.unlink()
                except PermissionError:
                    stats.temp_files_delete_failed += 1
                    log(f"DELETE_TEMP_FAILED {temp_file}", verbose=verbose)


def unique_conflict_path(dest: Path, source_label: str) -> Path:
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    candidate = parent / f"{stem}__from_{source_label}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = parent / f"{stem}__from_{source_label}_{counter}{suffix}"
        counter += 1
    return candidate


def ensure_dir(path: Path, *, apply: bool, stats: MergeStats, verbose: bool) -> None:
    if path.exists():
        return
    stats.dirs_created += 1
    log(f"MKDIR {path}", verbose=verbose)
    if apply:
        path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest: Path, source_label: str, *, apply: bool, stats: MergeStats, verbose: bool) -> None:
    final_dest = dest
    if final_dest.exists():
        if final_dest.is_file() and src.stat().st_size == final_dest.stat().st_size and file_md5(src) == file_md5(final_dest):
            stats.files_skipped_identical += 1
            log(f"SKIP_IDENTICAL {src} -> {final_dest}", verbose=verbose)
            return
        final_dest = unique_conflict_path(dest, source_label)
        stats.files_renamed_conflict += 1
        log(f"RENAME_CONFLICT {src} -> {final_dest}", verbose=verbose)
    else:
        log(f"COPY {src} -> {final_dest}", verbose=verbose)
    stats.files_copied += 1
    if apply:
        final_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, final_dest)


def merge_child_dir(source_dir: Path, child_dir: Path, target_root: Path, *, apply: bool, stats: MergeStats, verbose: bool) -> None:
    source_label = source_dir.name.replace(" ", "").replace("(", "").replace(")", "")
    target_child = target_root / child_dir.name
    ensure_dir(target_child, apply=apply, stats=stats, verbose=verbose)
    for path in sorted(child_dir.rglob("*")):
        if is_temp_file(path):
            continue
        rel = path.relative_to(child_dir)
        dest = target_child / rel
        if path.is_dir():
            ensure_dir(dest, apply=apply, stats=stats, verbose=verbose)
        elif path.is_file():
            ensure_dir(dest.parent, apply=apply, stats=stats, verbose=verbose)
            copy_file(path, dest, source_label, apply=apply, stats=stats, verbose=verbose)


def merge_sources(*, apply: bool, verbose: bool) -> MergeStats:
    stats = MergeStats()
    sources = discover_source_dirs()
    target = ZHONGKE_ROOT / TARGET_NAME
    if not sources:
        raise RuntimeError(f"No source dirs found under {ZHONGKE_ROOT} with prefix {SOURCE_PREFIX}")

    print(f"Mode: {'APPLY' if apply else 'DRY_RUN'}")
    print(safe_text(f"Target: {target}"))
    print(f"Sources: {len(sources)}")
    for source in sources:
        print(safe_text(f"  - {source.name}"))

    cleanup_temp_files(sources + [target], apply=apply, stats=stats, verbose=verbose)
    ensure_dir(target, apply=apply, stats=stats, verbose=verbose)

    for source in sources:
        for child in sorted(path for path in source.iterdir() if path.is_dir() and not path.name.startswith("._")):
            merge_child_dir(source, child, target, apply=apply, stats=stats, verbose=verbose)

    cleanup_temp_files([target], apply=apply, stats=stats, verbose=verbose)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge Zhongke 2026.05.14 package child directories into one target directory."
    )
    parser.add_argument("--apply", action="store_true", help="Actually copy files and delete ._* temp files.")
    parser.add_argument("--verbose", action="store_true", help="Print every delete/copy operation.")
    args = parser.parse_args()
    stats = merge_sources(apply=args.apply, verbose=args.verbose)
    print("Summary:")
    print(f"  temp_files_deleted: {stats.temp_files_deleted}")
    print(f"  temp_files_delete_failed: {stats.temp_files_delete_failed}")
    print(f"  dirs_created: {stats.dirs_created}")
    print(f"  files_copied: {stats.files_copied}")
    print(f"  files_skipped_identical: {stats.files_skipped_identical}")
    print(f"  files_renamed_conflict: {stats.files_renamed_conflict}")


if __name__ == "__main__":
    main()
