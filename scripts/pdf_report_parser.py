from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class PdfReportInfo:
    report_time: pd.Timestamp | None = None
    case_id: str = ""
    name: str = ""
    gender: str = ""
    age: str = ""
    phone_masked: str = ""
    text: str = ""


def _pdftotext_command() -> str | None:
    command = shutil.which("pdftotext")
    if command:
        return command
    texlive = Path(r"D:\Program Files\Latex\texlive\bin\win32\pdftotext.exe")
    if texlive.exists():
        return str(texlive)
    return None


def extract_pdf_text(pdf_path: Path) -> str:
    command = _pdftotext_command()
    if command is None or not pdf_path.exists():
        return ""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "report.txt"
        result = subprocess.run(
            [command, "-enc", "UTF-8", str(pdf_path), str(output)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0 or not output.exists():
            return ""
        return output.read_text(encoding="utf-8", errors="ignore")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _search(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def parse_pdf_report(pdf_path: Path) -> PdfReportInfo:
    text = extract_pdf_text(pdf_path)
    compact = _compact(text)
    case_id = _search(r"档案编号[:：]\s*([0-9]{13,})", compact)
    name = _search(r"姓名[:：]\s*([\u4e00-\u9fffA-Za-z·•]{2,20}?)(?:性别|年龄|出生日期|民族|婚姻状况|$)", compact)
    gender = _search(r"性别[:：]\s*([\u4e00-\u9fffA-Za-z]+?)(?:年龄|出生日期|民族|婚姻状况|$)", compact)
    age = _search(r"年龄[:：]\s*([0-9]+岁?)(?:出生日期|民族|婚姻状况|$)", compact)
    phone_masked = _search(r"电话[:：]\s*([0-9*]{6,16})", compact)
    report_time_text = _search(r"评估日期[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[0-9:：]{4,8})", compact)
    report_time = None
    if report_time_text:
        normalized = report_time_text.replace("：", ":")
        normalized = re.sub(r"^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}(?::\d{2})?)$", r"\1 \2", normalized)
        try:
            report_time = pd.Timestamp(pd.to_datetime(normalized))
        except Exception:
            report_time = None
    return PdfReportInfo(
        report_time=report_time,
        case_id=case_id,
        name=name,
        gender=gender,
        age=age,
        phone_masked=phone_masked,
        text=text,
    )
