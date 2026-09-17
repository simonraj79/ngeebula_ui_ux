"""Build an auditable station reference from LTA DataMall static files.

The network is used only when --download is passed. Tests and normal validation
operate on local files or the committed JSON artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable


STATIONS_URL = (
    "https://datamall.lta.gov.sg/content/dam/datamall/datasets/Geospatial/"
    "Train%20Station%20Codes%20and%20Chinese%20Names.zip"
)
LINES_URL = (
    "https://datamall.lta.gov.sg/content/dam/datamall/datasets/"
    "PublicTransportRelated/Train%20Line%20Codes.xlsx"
)
LICENCE_URL = (
    "https://datamall.lta.gov.sg/content/datamall/en/"
    "SingaporeOpenDataLicence.html"
)
EXPECTED_STATION_COLUMNS = {
    "stn_code",
    "mrt_station_english",
    "mrt_station_chinese",
    "mrt_line_english",
    "mrt_line_chinese",
}
EXPECTED_LINE_COLUMNS = {
    "MRT/LRT Line",
    "MRT/LRT Description",
    "MRT/LRT Direction",
    "Shuttle Direction",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _code_prefix(station_code: str) -> str:
    match = re.fullmatch(r"([A-Z]+)(\d*)", station_code)
    if not match:
        raise ValueError(f"Invalid LTA station code: {station_code!r}")
    return match.group(1)


def normalize_station_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Preserve each published code/line row without inferring memberships."""
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in rows:
        station_code = _clean(raw.get("stn_code")).upper()
        name = _clean(raw.get("mrt_station_english"))
        chinese_name = _clean(raw.get("mrt_station_chinese"))
        line_name = _clean(raw.get("mrt_line_english"))
        chinese_line_name = _clean(raw.get("mrt_line_chinese"))
        if not all((station_code, name, line_name)):
            raise ValueError(f"Incomplete station row: {raw!r}")
        if station_code in seen:
            raise ValueError(f"Duplicate station code in LTA source: {station_code}")
        seen.add(station_code)
        result.append(
            {
                "station_code": station_code,
                "code_prefix": _code_prefix(station_code),
                "station_name": name,
                "station_name_chinese": chinese_name,
                "published_line_name": line_name,
                "published_line_name_chinese": chinese_line_name,
            }
        )
    return sorted(
        result,
        key=lambda row: (
            row["code_prefix"],
            int(re.search(r"\d+", row["station_code"])[0])
            if re.search(r"\d+", row["station_code"])
            else -1,
        ),
    )


def normalize_line_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Retain LTA's line catalog verbatim; duplicate codes have distinct descriptions."""
    result = []
    for raw in rows:
        code = _clean(raw.get("MRT/LRT Line")).upper()
        description = _clean(raw.get("MRT/LRT Description"))
        if not code or not description:
            raise ValueError(f"Incomplete line row: {raw!r}")
        result.append(
            {
                "published_line_code": code,
                "published_description": description,
                "published_direction": _clean(raw.get("MRT/LRT Direction")),
                "published_shuttle_direction": _clean(raw.get("Shuttle Direction")),
            }
        )
    return result


def _read_excel_records(path: Path, expected_columns: set[str]) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - environment-specific message
        raise RuntimeError("pandas is required to import the LTA spreadsheets") from exc
    try:
        frame = pd.read_excel(path)
    except ImportError as exc:  # pragma: no cover - environment-specific message
        raise RuntimeError(
            "Reading LTA .xls/.xlsx files requires xlrd and openpyxl respectively"
        ) from exc
    missing = expected_columns - set(frame.columns)
    if missing:
        raise ValueError(f"Unexpected schema in {path.name}; missing {sorted(missing)}")
    return frame.to_dict(orient="records")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Ngeebula-LTA-reference-import/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def build_reference(
    station_rows: Iterable[dict[str, Any]],
    line_rows: Iterable[dict[str, Any]],
    *,
    retrieved_on: str,
    station_sha256: str,
    line_sha256: str,
) -> dict[str, Any]:
    stations = normalize_station_rows(station_rows)
    lines = normalize_line_rows(line_rows)
    return {
        "schema_version": 1,
        "provenance": {
            "publisher": "Land Transport Authority, Singapore",
            "retrieved_on": retrieved_on,
            "licence": "Singapore Open Data Licence 1.0",
            "licence_url": LICENCE_URL,
            "station_source": {
                "title": "Train Station Codes and Chinese Names",
                "url": STATIONS_URL,
                "portal_last_update": "Jan 2025",
                "sha256": station_sha256,
            },
            "line_source": {
                "title": "Train Lines Codes",
                "url": LINES_URL,
                "portal_last_update": "Feb 2024",
                "sha256": line_sha256,
            },
            "transform": (
                "One output station record per published source row. No station, line, "
                "interchange, depot, track, asset, or ownership membership is inferred."
            ),
        },
        "summary": {
            "station_code_count": len(stations),
            "station_name_count": len({row["station_name"] for row in stations}),
            "published_station_line_counts": dict(
                sorted(Counter(row["published_line_name"] for row in stations).items())
            ),
            "line_catalog_row_count": len(lines),
        },
        "stations": stations,
        "line_catalog": lines,
    }


def _source_paths(args: argparse.Namespace, workdir: Path) -> tuple[Path, Path, str, str]:
    if args.download:
        station_zip = _download(STATIONS_URL)
        line_bytes = _download(LINES_URL)
        station_sha = _sha256(station_zip)
        line_sha = _sha256(line_bytes)
        with zipfile.ZipFile(io.BytesIO(station_zip)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".xls")]
            if len(members) != 1:
                raise ValueError(f"Expected one .xls station file, found {members}")
            station_path = workdir / Path(members[0]).name
            station_path.write_bytes(archive.read(members[0]))
        line_path = workdir / "Train Line Codes.xlsx"
        line_path.write_bytes(line_bytes)
        return station_path, line_path, station_sha, line_sha
    if not args.stations_file or not args.lines_file:
        raise ValueError("Pass --download or both --stations-file and --lines-file")
    station_path = Path(args.stations_file)
    line_path = Path(args.lines_file)
    return (
        station_path,
        line_path,
        _sha256(station_path.read_bytes()),
        _sha256(line_path.read_bytes()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download both official LTA files")
    parser.add_argument("--stations-file", type=Path, help="Extracted official station .xls")
    parser.add_argument("--lines-file", type=Path, help="Official line-code .xlsx")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retrieved-on", default=date.today().isoformat())
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ngeebula-lta-") as temp:
        station_path, line_path, station_sha, line_sha = _source_paths(args, Path(temp))
        reference = build_reference(
            _read_excel_records(station_path, EXPECTED_STATION_COLUMNS),
            _read_excel_records(line_path, EXPECTED_LINE_COLUMNS),
            retrieved_on=args.retrieved_on,
            station_sha256=station_sha,
            line_sha256=line_sha,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reference, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {reference['summary']['station_code_count']} station codes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
