from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import openpyxl
import xlrd


def u(text: str) -> str:
    return text.encode('ascii').decode('unicode_escape')


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWN_ROOTS = {'datasets', 'docs', 'frontend', 'scripts', '__pycache__'}
OUTPUT_ROOT = PROJECT_ROOT / u('\\u56db\\u8bca\\u4eea\\u6570\\u636e\\u6574\\u7406')
SOURCE_ROOT = next(
    path
    for path in PROJECT_ROOT.iterdir()
    if path.is_dir()
    and path.name not in KNOWN_ROOTS
    and path.name != OUTPUT_ROOT.name
    and u('\\u6570\\u636e\\u6c47\\u603b') in path.name
)
REPORT_ROOT = PROJECT_ROOT / 'datasets' / 'directory_dedup'
MANIFEST_CSV = REPORT_ROOT / 'qz_package_reorg_manifest.csv'
SUMMARY_CSV = REPORT_ROOT / 'qz_package_reorg_summary.csv'

GENERIC_NAME_PARTS = {
    u('\\u5c0f\\u56db\\u8bca\\u4eea'),
    u('\\u5927\\u56db\\u8bca\\u4eea'),
    u('\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea'),
    u('\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea\\u4e8c\\u4ee3'),
    u('\\u7389\\u751f\\u5802\\u56db\\u8bca\\u4eea'),
    u('\\u8109'),
    u('\\u820c'),
    u('\\u9762'),
    u('\\u95ee'),
    u('\\u95ee\\u8bca'),
    u('\\u8109\\u8bca'),
    u('\\u820c\\u8bca'),
    u('\\u9762\\u8bca'),
    u('\\u62a5\\u544a'),
    u('\\u75c5\\u5386\\u6570\\u636e'),
    u('\\u5b9e\\u9a8c\\u5ba4\\u8bb0\\u5f55\\u8868'),
}

CHINESE_NAME_RE = re.compile(r'^[\u4e00-\u9fff]{2,4}$')
JSON_NAME_RE = re.compile(r'"CaName"\s*:\s*"([^"]+)"')
FILENAME_NAME_RE = re.compile(r'([\u4e00-\u9fff]{2,4})[_\(\uff08 ]')
DATE_RANGE_RE = re.compile(r'(20\d{2})[.\-](\d{1,2})[.\-](\d{1,2})\s*[~\-]\s*(?:(20\d{2})[.\-])?(\d{1,2})[.\-](\d{1,2})')
LABEL_NAME = u('\\u59d3\\u540d')
UNKNOWN_NAME = u('\\u672a\\u8bc6\\u522b\\u59d3\\u540d')
UNKNOWN_BATCH = u('\\u5386\\u53f2\\u6279\\u6b21')


@dataclass
class PackageRecord:
    relative_path: str
    source_top: str
    file_count: int
    total_bytes: int
    content_fingerprint: str
    canonical_path: str
    duplicate_group_size: int
    is_group_representative: bool
    device_kind: str
    date_range: str
    person_name: str
    target_relative_path: str
    operation: str


def ensure_dirs() -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def file_sha1(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open('rb') as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def dir_fingerprint(dir_path: Path) -> tuple[str, int, int]:
    entries: list[str] = []
    file_count = 0
    total_size = 0
    for path in sorted(item for item in dir_path.rglob('*') if item.is_file()):
        rel = path.relative_to(dir_path).as_posix()
        size = path.stat().st_size
        digest = file_sha1(path)
        entries.append(f'{rel}\t{size}\t{digest}')
        file_count += 1
        total_size += size
    fingerprint = hashlib.sha1('\n'.join(entries).encode('utf-8')).hexdigest()
    return fingerprint, file_count, total_size


def collect_effective_dirs(base: Path) -> list[Path]:
    effective: list[Path] = []
    stack = [base]
    while stack:
        current = stack.pop()
        children = list(current.iterdir())
        files = [child for child in children if child.is_file()]
        dirs = sorted((child for child in children if child.is_dir()), key=lambda path: path.name, reverse=True)
        if files:
            effective.append(current)
        elif dirs:
            stack.extend(dirs)
    return sorted(set(effective), key=lambda path: path.relative_to(base).as_posix())


def normalize_date_range(text: str) -> str:
    match = DATE_RANGE_RE.search(text)
    if match:
        start_year = int(match.group(1))
        start_month = int(match.group(2))
        start_day = int(match.group(3))
        end_year = int(match.group(4) or match.group(1))
        end_month = int(match.group(5))
        end_day = int(match.group(6))
        return f'{start_year:04d}.{start_month:02d}.{start_day:02d}-{end_year:04d}.{end_month:02d}.{end_day:02d}'
    if '11.09-12.10' in text:
        return '2025.11.09-2025.12.10'
    if u('\\u0031\\u6708') in text:
        return '2026.01'
    if u('\\u0032\\u6708') in text:
        return '2026.02'
    if '3.1-31' in text or '3.1-3.31' in text:
        return '2026.03'
    if '4.1' in text or '04.1' in text or '04.01' in text:
        return '2026.04'
    return UNKNOWN_BATCH


def normalize_device_kind(source_top: str) -> str:
    if u('\\u7389\\u751f\\u5802') in source_top:
        return u('\\u7389\\u751f\\u5802\\u56db\\u8bca\\u4eea')
    if u('\\u5927\\u56db\\u8bca\\u4eea') in source_top:
        return u('\\u5927\\u56db\\u8bca\\u4eea')
    if u('\\u5c0f\\u56db\\u8bca\\u4eea\\u4e8c\\u4ee3') in source_top:
        return u('\\u5c0f\\u56db\\u8bca\\u4eea\\u4e8c\\u4ee3')
    if u('\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea\\u4e8c\\u4ee3') in source_top:
        return u('\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea\\u4e8c\\u4ee3')
    if u('\\u4e00\\u4ee3\\u5c0f\\u56db\\u8bca\\u4eea') in source_top or u('\\u5c0f\\u56db\\u8bca\\u4eea\\u4e00\\u4ee3') in source_top:
        return u('\\u5c0f\\u56db\\u8bca\\u4eea\\u4e00\\u4ee3')
    if source_top.startswith(u('\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea')):
        return u('\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea')
    if u('\\u5b9e\\u9a8c\\u5ba4\\u8bb0\\u5f55\\u8868') in source_top:
        return u('\\u5b9e\\u9a8c\\u5ba4\\u8bb0\\u5f55\\u8868')
    return source_top


def is_name_candidate(part: str) -> bool:
    text = str(part).strip()
    return bool(text) and CHINESE_NAME_RE.fullmatch(text) is not None and text not in GENERIC_NAME_PARTS


def scan_json_name(path: Path) -> str | None:
    text = None
    for encoding in ('utf-8', 'utf-8-sig', 'gb18030'):
        try:
            text = path.read_text(encoding=encoding)
            break
        except Exception:
            continue
    if text is None:
        return None
    match = JSON_NAME_RE.search(text)
    if match and is_name_candidate(match.group(1)):
        return match.group(1)
    return None


def iter_candidate_names_from_workbook(path: Path) -> Iterable[str]:
    raw = path.read_bytes()
    if raw[:2] == b'PK':
        try:
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception:
            workbook = None
        if workbook is None:
            return
        try:
            for sheet in workbook.worksheets[:2]:
                for row in sheet.iter_rows(min_row=1, max_row=60, max_col=40, values_only=True):
                    values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                    for idx, value in enumerate(values):
                        if value == LABEL_NAME and idx + 1 < len(values) and is_name_candidate(values[idx + 1]):
                            yield values[idx + 1]
                        if is_name_candidate(value):
                            yield value
        finally:
            workbook.close()
    elif raw[:8] == bytes.fromhex('D0CF11E0A1B11AE1'):
        try:
            workbook = xlrd.open_workbook(file_contents=raw, on_demand=True)
        except Exception:
            workbook = None
        if workbook is None:
            return
        try:
            for sheet in workbook.sheets()[:2]:
                for row_idx in range(min(sheet.nrows, 60)):
                    values = [str(value).strip() for value in sheet.row_values(row_idx) if str(value).strip()]
                    for idx, value in enumerate(values):
                        if value == LABEL_NAME and idx + 1 < len(values) and is_name_candidate(values[idx + 1]):
                            yield values[idx + 1]
                        if is_name_candidate(value):
                            yield value
        finally:
            workbook.release_resources()


def extract_person_name(dir_path: Path) -> str:
    relative = dir_path.relative_to(SOURCE_ROOT)
    for part in relative.parts[1:]:
        if is_name_candidate(part):
            return part
    for child in sorted(dir_path.rglob('*')):
        if not child.is_file():
            continue
        if child.suffix.lower() == '.json':
            name = scan_json_name(child)
            if name:
                return name
        match = FILENAME_NAME_RE.search(child.name)
        if match and is_name_candidate(match.group(1)):
            return match.group(1)
    for child in sorted(dir_path.iterdir()):
        if child.is_file() and child.suffix.lower() in {'.xls', '.xlsx'}:
            for name in iter_candidate_names_from_workbook(child):
                if is_name_candidate(name):
                    return name
    return UNKNOWN_NAME


def make_relative_target(dir_path: Path, source_top: str, person_name: str) -> Path:
    parts = list(dir_path.relative_to(SOURCE_ROOT).parts)
    name_index = -1
    for idx, part in enumerate(parts[1:], start=1):
        if part == person_name:
            name_index = idx
            break
    if name_index >= 0:
        tail_parts = parts[name_index + 1:]
        return Path(*tail_parts) if tail_parts else Path(source_top)
    return Path(parts[-1]) if len(parts) > 1 else Path(source_top)


def sanitize_path_component(text: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', '_', text.strip())
    sanitized = sanitized.rstrip('. ')
    return sanitized or 'unnamed'


def unique_target_path(target_path: Path) -> Path:
    current = target_path
    counter = 1
    while current.exists():
        current = target_path.parent / f'{target_path.name}__{counter:02d}'
        counter += 1
    return current


def build_records() -> list[PackageRecord]:
    effective_dirs = collect_effective_dirs(SOURCE_ROOT)
    rows: list[dict[str, object]] = []
    groups: dict[str, list[str]] = {}
    for dir_path in effective_dirs:
        fingerprint, file_count, total_bytes = dir_fingerprint(dir_path)
        if file_count == 0:
            continue
        relative = dir_path.relative_to(SOURCE_ROOT).as_posix()
        groups.setdefault(fingerprint, []).append(relative)
        rows.append({
            'relative_path': relative,
            'source_top': dir_path.relative_to(SOURCE_ROOT).parts[0],
            'file_count': file_count,
            'total_bytes': total_bytes,
            'content_fingerprint': fingerprint,
        })
    records: list[PackageRecord] = []
    reserved_targets: set[str] = set()
    for row in sorted(rows, key=lambda item: item['relative_path']):
        relative_path = str(row['relative_path'])
        source_top = str(row['source_top'])
        dir_path = SOURCE_ROOT / Path(relative_path)
        fingerprint = str(row['content_fingerprint'])
        canonical_path = sorted(groups[fingerprint])[0]
        duplicate_group_size = len(groups[fingerprint])
        is_group_representative = relative_path == canonical_path
        device_kind = normalize_device_kind(source_top)
        date_range = normalize_date_range(source_top)
        person_name = extract_person_name(dir_path)
        tail = make_relative_target(dir_path, source_top, person_name)
        target_relative = Path(
            sanitize_path_component(device_kind),
            sanitize_path_component(date_range),
            sanitize_path_component(person_name),
            *[sanitize_path_component(part) for part in tail.parts],
        )
        while target_relative.as_posix() in reserved_targets:
            target_relative = target_relative.parent / f'{target_relative.name}__dup'
        if is_group_representative:
            reserved_targets.add(target_relative.as_posix())
        records.append(PackageRecord(
            relative_path=relative_path,
            source_top=source_top,
            file_count=int(row['file_count']),
            total_bytes=int(row['total_bytes']),
            content_fingerprint=fingerprint,
            canonical_path=canonical_path,
            duplicate_group_size=duplicate_group_size,
            is_group_representative=is_group_representative,
            device_kind=device_kind,
            date_range=date_range,
            person_name=person_name,
            target_relative_path=target_relative.as_posix(),
            operation='move_to_organized_root' if is_group_representative else 'delete_duplicate',
        ))
    return records


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def remove_empty_dirs(base: Path) -> int:
    removed = 0
    for path in sorted((item for item in base.rglob('*') if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
            removed += 1
        except Exception:
            continue
    return removed


def execute(records: list[PackageRecord]) -> dict[str, int]:
    moved = 0
    deleted = 0
    skipped = 0
    for record in records:
        source_path = SOURCE_ROOT / Path(record.relative_path)
        if not source_path.exists():
            skipped += 1
            continue
        if record.operation == 'move_to_organized_root':
            target_path = unique_target_path(OUTPUT_ROOT / Path(record.target_relative_path))
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_path), str(target_path))
            moved += 1
        else:
            shutil.rmtree(source_path)
            deleted += 1
    empty_removed = remove_empty_dirs(SOURCE_ROOT)
    return {'moved': moved, 'deleted': deleted, 'skipped': skipped, 'empty_dirs_removed': empty_removed}


def main() -> None:
    ensure_dirs()
    records = build_records()
    write_csv(MANIFEST_CSV, [record.__dict__ for record in records])
    summary = execute(records)
    write_csv(SUMMARY_CSV, [summary])
    print(json.dumps({
        'source_root': str(SOURCE_ROOT),
        'output_root': str(OUTPUT_ROOT),
        'manifest_csv': str(MANIFEST_CSV),
        'summary_csv': str(SUMMARY_CSV),
        'package_count': len(records),
        **summary,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
