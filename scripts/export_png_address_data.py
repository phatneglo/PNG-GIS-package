#!/usr/bin/env python3
"""Export PNG address records to JSON, CSV, XML, and SQL packages."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


DEFAULT_COLUMNS = [
    "record_id",
    "code",
    "name",
    "level",
    "label",
    "path",
    "country_code",
    "country_name",
    "region_code",
    "region_name",
    "province_code",
    "province_name",
    "district_code",
    "district_name",
    "llg_code",
    "llg_name",
    "ward_code",
    "ward_name",
    "ward_number",
    "code_system",
    "standard_code",
    "is_standard_code",
    "source_code",
    "source_code_column",
    "code_note",
    "source_dataset",
    "source_url",
    "matched_to_map",
    "has_boundary",
    "geometry_available",
    "source_province_name",
    "source_district_name",
    "source_llg_name",
    "next_level",
    "child_level",
    "child_records_available",
    "child_record_note",
]

INTEGER_COLUMNS = {"ward_number"}
BOOLEAN_COLUMNS = {
    "is_standard_code",
    "matched_to_map",
    "has_boundary",
    "geometry_available",
    "child_records_available",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export generated PNG address JSON to common data formats.")
    parser.add_argument("--address-root", default="png-json-address", help="Root folder containing generated png-json-address/<year> files.")
    parser.add_argument("--out", default="address-data", help="Output root for export packages.")
    parser.add_argument("--year", default=None, help="Single year to export. Defaults to all year folders under address-root.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    address_root = Path(args.address_root)
    out_root = Path(args.out)
    years = [args.year] if args.year else discover_years(address_root)

    if not years:
        raise SystemExit(f"No address year folders found under {address_root}")

    for year in years:
        export_year(address_root, out_root, str(year))


def discover_years(address_root: Path) -> list[str]:
    if not address_root.exists():
        return []
    years = [path.name for path in address_root.iterdir() if path.is_dir() and (path / "address-flat.json").exists()]
    return sorted(years, key=lambda value: int(value) if value.isdigit() else value)


def export_year(address_root: Path, out_root: Path, year: str) -> None:
    source_dir = address_root / year
    flat_path = source_dir / "address-flat.json"
    hierarchy_path = source_dir / "address-hierarchy.json"

    if not flat_path.exists():
        raise FileNotFoundError(f"Missing flat address file: {flat_path}")
    if not hierarchy_path.exists():
        raise FileNotFoundError(f"Missing hierarchy address file: {hierarchy_path}")

    flat_data = json.loads(flat_path.read_text(encoding="utf-8"))
    hierarchy_data = json.loads(hierarchy_path.read_text(encoding="utf-8"))
    records = normalize_records(flat_data.get("records", []))
    columns = collect_columns(records)
    export_dir = out_root / year
    export_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    metadata = build_metadata(year, generated_at, records, columns, flat_data, hierarchy_data)
    schema = build_schema(columns)

    write_json(export_dir / "metadata.json", metadata)
    write_json(export_dir / "schema.json", schema)
    write_json(export_dir / "address-records.json", {
        "metadata": metadata,
        "schema": schema,
        "records": records,
    })
    write_json(export_dir / "address-hierarchy.json", hierarchy_data)
    write_csv(export_dir / "address-records.csv", records, columns)
    write_xml(export_dir / "address-records.xml", records, columns, metadata)
    write_sql(export_dir / "png-address-data.sql", records, columns, metadata)
    write_readme(export_dir / "README.md", year, metadata)

    print(f"Wrote {export_dir} ({len(records):,} records).")


def normalize_records(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in raw_records:
        record = dict(raw)
        for column in BOOLEAN_COLUMNS:
            if column in record and record[column] not in ("", None):
                record[column] = bool(record[column])
        for column in INTEGER_COLUMNS:
            if column in record and record[column] not in ("", None):
                try:
                    record[column] = int(record[column])
                except (TypeError, ValueError):
                    record[column] = None
        records.append(record)

    sorted_records = sorted(records, key=lambda item: (
        str(item.get("level", "")),
        str(item.get("region_code", "")),
        str(item.get("province_code", "")),
        str(item.get("district_code", "")),
        str(item.get("llg_code", "")),
        int(item.get("ward_number") or 0),
        str(item.get("code", "")),
    ))
    for index, record in enumerate(sorted_records, start=1):
        record["record_id"] = f"PNG-{index:06d}"
    return sorted_records


def collect_columns(records: list[dict[str, Any]]) -> list[str]:
    columns = [column for column in DEFAULT_COLUMNS if any(column in record for record in records)]
    for record in records:
        for column in record:
            if column not in columns:
                columns.append(column)
    return columns


def build_metadata(
    year: str,
    generated_at: str,
    records: list[dict[str, Any]],
    columns: list[str],
    flat_data: dict[str, Any],
    hierarchy_data: dict[str, Any],
) -> dict[str, Any]:
    level_counts: dict[str, int] = {}
    code_counts: dict[str, int] = {}
    for record in records:
        level = str(record.get("level", "unknown"))
        level_counts[level] = level_counts.get(level, 0) + 1
        code = str(record.get("code", ""))
        code_counts[code] = code_counts.get(code, 0) + 1

    return {
        "name": "Papua New Guinea Address Data",
        "slug": "png-address-data",
        "year": str(year),
        "country": flat_data.get("country", {"code": "PNG", "name": "Papua New Guinea"}),
        "generated_at_utc": generated_at,
        "source_generated_at_utc": flat_data.get("generated_at_utc", ""),
        "record_count": len(records),
        "level_counts": level_counts,
        "duplicate_code_count": sum(1 for count in code_counts.values() if count > 1),
        "columns": columns,
        "formats": ["json", "csv", "xml", "sql"],
        "encoding": "UTF-8",
        "hierarchy": hierarchy_data.get("administrative_hierarchy", []),
        "sources": hierarchy_data.get("sources", []),
        "supplemental_sources": hierarchy_data.get("supplemental_sources", []),
        "stats": hierarchy_data.get("stats", {}),
        "notes": [
            "Province codes use ISO 3166-2:PG where available.",
            "District, LLG, and supplemental ward codes may be generated package codes when no official source code is available.",
            "Ward records are address/search records only unless geometry_available is true.",
        ],
    }


def build_schema(columns: list[str]) -> dict[str, Any]:
    return {
        "table": "png_address_records",
        "primary_key": "record_id",
        "columns": [
            {
                "name": column,
                "type": column_type(column),
                "nullable": column != "code",
                "description": column_description(column),
            }
            for column in columns
        ],
    }


def column_type(column: str) -> str:
    if column in BOOLEAN_COLUMNS:
        return "boolean"
    if column in INTEGER_COLUMNS:
        return "integer"
    if column == "path":
        return "json_array"
    return "string"


def column_description(column: str) -> str:
    descriptions = {
        "record_id": "Unique deterministic row identifier for this exported dataset.",
        "code": "Stable record identifier in this data package.",
        "name": "Short display name for the address record.",
        "level": "Administrative level: region, province, district, llg, or ward.",
        "label": "Full readable address label.",
        "path": "Ancestor names from nearest parent to country.",
        "code_system": "Code authority or generated-code namespace.",
        "standard_code": "Official/standard code where known.",
        "is_standard_code": "True when code is from a known official/standard source.",
        "matched_to_map": "True when a supplemental address record matched a generated map boundary parent.",
        "geometry_available": "True when this address level has boundary geometry in the map package.",
    }
    return descriptions.get(column, column.replace("_", " ").capitalize())


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, records: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({column: csv_value(record.get(column)) for column in columns})


def write_xml(path: Path, records: list[dict[str, Any]], columns: list[str], metadata: dict[str, Any]) -> None:
    root = ET.Element("pngAddressData", {
        "year": str(metadata["year"]),
        "countryCode": str(metadata["country"].get("code", "PNG")),
        "generatedAtUtc": str(metadata["generated_at_utc"]),
        "recordCount": str(metadata["record_count"]),
    })
    metadata_node = ET.SubElement(root, "metadata")
    ET.SubElement(metadata_node, "name").text = str(metadata["name"])
    ET.SubElement(metadata_node, "encoding").text = "UTF-8"

    records_node = ET.SubElement(root, "records")
    for record in records:
        record_node = ET.SubElement(records_node, "record", {
            "recordId": str(record.get("record_id", "")),
            "level": str(record.get("level", "")),
        })
        for column in columns:
            value = record.get(column)
            if value in (None, ""):
                continue
            child = ET.SubElement(record_node, xml_tag(column))
            child.text = xml_value(value)

    indent_xml(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_sql(path: Path, records: list[dict[str, Any]], columns: list[str], metadata: dict[str, Any]) -> None:
    lines = [
        "-- Papua New Guinea Address Data",
        f"-- Year: {metadata['year']}",
        f"-- Generated at UTC: {metadata['generated_at_utc']}",
        "-- SQL dialect: PostgreSQL-compatible; TEXT columns keep imports portable.",
        "",
        "BEGIN;",
        "",
        "DROP TABLE IF EXISTS png_address_records;",
        "CREATE TABLE png_address_records (",
    ]
    column_lines = []
    for column in columns:
        sql_type = sql_column_type(column)
        not_null = " NOT NULL" if column in {"record_id", "code"} else ""
        column_lines.append(f"  {sql_identifier(column)} {sql_type}{not_null}")
    column_lines.append("  PRIMARY KEY (record_id)")
    lines.append(",\n".join(column_lines))
    lines.extend([
        ");",
        "",
        "DROP TABLE IF EXISTS png_address_metadata;",
        "CREATE TABLE png_address_metadata (",
        "  key TEXT PRIMARY KEY,",
        "  value TEXT NOT NULL",
        ");",
        "",
    ])

    for key, value in {
        "name": metadata["name"],
        "year": metadata["year"],
        "country_code": metadata["country"].get("code", "PNG"),
        "country_name": metadata["country"].get("name", "Papua New Guinea"),
        "generated_at_utc": metadata["generated_at_utc"],
        "record_count": metadata["record_count"],
        "duplicate_code_count": metadata["duplicate_code_count"],
        "level_counts": metadata["level_counts"],
    }.items():
        lines.append(f"INSERT INTO png_address_metadata (key, value) VALUES ({sql_literal(key)}, {sql_literal(value)});")

    if records:
        quoted_columns = ", ".join(sql_identifier(column) for column in columns)
        for record in records:
            values = ", ".join(sql_literal(record.get(column)) for column in columns)
            lines.append(f"INSERT INTO png_address_records ({quoted_columns}) VALUES ({values});")

    lines.extend([
        "",
        "CREATE INDEX idx_png_address_records_level ON png_address_records (level);",
        "CREATE INDEX idx_png_address_records_code ON png_address_records (code);",
        "CREATE INDEX idx_png_address_records_province_code ON png_address_records (province_code);",
        "CREATE INDEX idx_png_address_records_district_code ON png_address_records (district_code);",
        "CREATE INDEX idx_png_address_records_llg_code ON png_address_records (llg_code);",
        "CREATE INDEX idx_png_address_records_label ON png_address_records (label);",
        "",
        "COMMIT;",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(path: Path, year: str, metadata: dict[str, Any]) -> None:
    lines = [
        f"# PNG Address Data {year}",
        "",
        "This folder contains the generated Papua New Guinea address package in common import formats.",
        "",
        "## Files",
        "",
        "- `address-records.json` - canonical flat records with metadata and schema.",
        "- `address-hierarchy.json` - nested country -> region -> province -> district -> LLG -> ward hierarchy.",
        "- `address-records.csv` - spreadsheet/import friendly flat records, UTF-8 with BOM.",
        "- `address-records.xml` - XML flat records with stable element names.",
        "- `png-address-data.sql` - PostgreSQL-compatible SQL table, metadata, inserts, and indexes.",
        "- `schema.json` - column definitions and data types.",
        "- `metadata.json` - generation metadata, counts, source notes, and hierarchy notes.",
        "",
        "## Counts",
        "",
    ]
    for level, count in metadata["level_counts"].items():
        lines.append(f"- `{level}`: {count:,}")
    lines.extend([
        "",
        "## Notes",
        "",
        "- Province codes use ISO 3166-2:PG where available.",
        "- District, LLG, and some ward codes are package-generated where no official code is available.",
        "- Ward records may be address/search records only; check `geometry_available` before treating a ward as a mapped polygon.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def xml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def xml_tag(value: str) -> str:
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    if not tag or not re.match(r"[A-Za-z_]", tag):
        tag = f"field_{tag}"
    return tag


def indent_xml(element: ET.Element, level: int = 0) -> None:
    indentation = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indentation + "  "
        for child in element:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indentation
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indentation


def sql_column_type(column: str) -> str:
    if column in BOOLEAN_COLUMNS:
        return "BOOLEAN"
    if column in INTEGER_COLUMNS:
        return "INTEGER"
    return "TEXT"


def sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sql_literal(value: Any) -> str:
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "'" + str(value).replace("'", "''") + "'"


if __name__ == "__main__":
    main()
