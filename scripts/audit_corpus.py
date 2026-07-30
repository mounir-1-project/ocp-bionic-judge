"""Extract the OCP source corpus and profile DATA.xlsx.

This script is intentionally read-only with respect to the source documents.
It writes auditable JSON and Markdown artefacts under ``tmp/corpus_audit``.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "tmp" / "corpus_audit"


def clean_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value).strip() if not isinstance(value, (int, float, bool)) else value


def extract_workbook(path: Path) -> dict[str, Any]:
    book = pd.ExcelFile(path)
    sheets: dict[str, Any] = {}
    for sheet_name in book.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet_name, header=None)
        frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
        rows = [
            [clean_value(value) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ]
        sheets[sheet_name] = {
            "rows": len(frame),
            "columns": len(frame.columns),
            "content": rows,
        }
    return {"file": path.name, "sheets": sheets}


def detect_header(raw: pd.DataFrame) -> int:
    """Choose the densest early row as the likely header row."""
    sample = raw.head(30)
    scores: list[tuple[float, int]] = []
    for idx, row in sample.iterrows():
        non_null = row.notna().sum()
        strings = sum(isinstance(value, str) for value in row.dropna())
        uniqueness = row.dropna().astype(str).nunique()
        scores.append((non_null + 0.5 * strings + 0.1 * uniqueness, int(idx)))
    return max(scores)[1]


def normalise_column(value: Any, index: int) -> str:
    text = re.sub(r"\s+", " ", str(value).strip())
    return text if text and text.lower() != "nan" else f"column_{index + 1}"


def profile_data(path: Path) -> dict[str, Any]:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    header_row = detect_header(raw)
    frame = pd.read_excel(path, sheet_name=0, header=header_row)
    frame.columns = [normalise_column(value, idx) for idx, value in enumerate(frame.columns)]
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")

    profile: dict[str, Any] = {
        "file": path.name,
        "header_row_zero_based": header_row,
        "shape": [int(frame.shape[0]), int(frame.shape[1])],
        "duplicate_rows": int(frame.duplicated().sum()),
        "columns": {},
    }

    numeric_frame = pd.DataFrame(index=frame.index)
    for column in frame.columns:
        series = frame[column]
        is_datetime = pd.api.types.is_datetime64_any_dtype(series)
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_ratio = 0.0 if is_datetime else float(numeric.notna().mean())
        quality_codes = sorted(
            {
                str(value).strip()
                for value in series.dropna()
                if isinstance(value, str) and pd.isna(pd.to_numeric(value, errors="coerce"))
            }
        )
        column_profile: dict[str, Any] = {
            "dtype_loaded": str(series.dtype),
            "missing": int(series.isna().sum()),
            "missing_pct": round(float(series.isna().mean() * 100), 4),
            "unique": int(series.nunique(dropna=True)),
            "numeric_ratio": round(numeric_ratio, 6),
            "quality_codes_or_text": quality_codes[:30],
        }
        if is_datetime:
            converted = pd.to_datetime(series, errors="coerce")
            ordered = converted.dropna().sort_values()
            diffs = ordered.diff().dropna()
            column_profile["datetime"] = {
                "start": clean_value(ordered.min()),
                "end": clean_value(ordered.max()),
                "duplicate_timestamps": int(converted.duplicated().sum()),
                "median_step": str(diffs.median()) if not diffs.empty else None,
                "largest_step": str(diffs.max()) if not diffs.empty else None,
            }
        elif numeric_ratio >= 0.5:
            numeric_frame[column] = numeric
            valid = numeric.dropna()
            if not valid.empty:
                quantiles = valid.quantile([0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1])
                q1, q3 = valid.quantile([0.25, 0.75])
                iqr = q3 - q1
                outliers = ((valid < q1 - 1.5 * iqr) | (valid > q3 + 1.5 * iqr)).sum()
                column_profile.update(
                    {
                        "mean": clean_value(valid.mean()),
                        "std": clean_value(valid.std()),
                        "quantiles": {str(key): clean_value(value) for key, value in quantiles.items()},
                        "iqr_outliers": int(outliers),
                        "iqr_outliers_pct": round(float(outliers / len(valid) * 100), 4),
                        "zero_count": int((valid == 0).sum()),
                        "longest_constant_run": longest_constant_run(valid),
                    }
                )
        else:
            values = series.dropna().astype(str)
            column_profile["top_values"] = values.value_counts().head(20).to_dict()
        profile["columns"][column] = column_profile

    if numeric_frame.shape[1] >= 2:
        correlation = numeric_frame.corr(min_periods=100)
        pairs: list[dict[str, Any]] = []
        for i, left in enumerate(correlation.columns):
            for right in correlation.columns[i + 1 :]:
                value = correlation.loc[left, right]
                if pd.notna(value):
                    pairs.append({"left": left, "right": right, "r": round(float(value), 6)})
        profile["top_absolute_correlations"] = sorted(
            pairs, key=lambda item: abs(item["r"]), reverse=True
        )[:50]

    date_candidates: dict[str, Any] = {}
    for column in frame.columns:
        series = frame[column]
        is_datetime = pd.api.types.is_datetime64_any_dtype(series)
        name_suggests_date = any(token in column.upper() for token in ("TIME", "DATE"))
        if not is_datetime and (
            pd.api.types.is_numeric_dtype(series) or not name_suggests_date
        ):
            continue
        converted = pd.to_datetime(frame[column], errors="coerce")
        if converted.notna().mean() >= 0.8:
            ordered = converted.dropna().sort_values()
            diffs = ordered.diff().dropna()
            date_candidates[column] = {
                "start": clean_value(ordered.min()),
                "end": clean_value(ordered.max()),
                "duplicate_timestamps": int(converted.duplicated().sum()),
                "median_step": str(diffs.median()) if not diffs.empty else None,
                "largest_step": str(diffs.max()) if not diffs.empty else None,
            }
    profile["datetime_candidates"] = date_candidates
    return profile


def longest_constant_run(series: pd.Series) -> int:
    if series.empty:
        return 0
    groups = series.ne(series.shift()).cumsum()
    return int(series.groupby(groups).size().max())


def extract_pdf(path: Path) -> dict[str, Any]:
    reader = PdfReader(path)
    return {
        "file": path.name,
        "pages": [
            {"page": index + 1, "text": page.extract_text() or ""}
            for index, page in enumerate(reader.pages)
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    xlsx_sources = sorted(DOCS.glob("*.xlsx"))
    legacy_sources = sorted(DOCS.glob("*.xls"))
    workbook_audits = [
        extract_workbook(path)
        for path in xlsx_sources + legacy_sources
        if path.name.lower() != "data.xlsx"
    ]
    pdf_audits = [extract_pdf(path) for path in sorted(DOCS.glob("*.pdf"))]
    dataset_profile = profile_data(DOCS / "DATA.xlsx")

    payload = {
        "workbooks": workbook_audits,
        "pdfs": pdf_audits,
        "dataset": dataset_profile,
    }
    (OUT / "corpus_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = ["# Extraction intégrale du corpus OCP", ""]
    for workbook in workbook_audits:
        lines.extend([f"## {workbook['file']}", ""])
        for sheet_name, sheet in workbook["sheets"].items():
            lines.extend([f"### Feuille : {sheet_name}", ""])
            for row in sheet["content"]:
                cells = [str(value) for value in row if value not in (None, "")]
                if cells:
                    lines.append(" | ".join(cells))
            lines.append("")
    for pdf in pdf_audits:
        lines.extend([f"## {pdf['file']}", ""])
        for page in pdf["pages"]:
            lines.extend([f"### Page {page['page']}", "", page["text"].strip(), ""])
    (OUT / "corpus_text.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(
        {
            "workbooks": [item["file"] for item in workbook_audits],
            "pdfs": [{"file": item["file"], "pages": len(item["pages"])} for item in pdf_audits],
            "dataset_shape": dataset_profile["shape"],
            "dataset_columns": list(dataset_profile["columns"]),
            "output": str(OUT),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
