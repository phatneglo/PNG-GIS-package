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
    write_cdms_admin_area_seed_sql(export_dir / "png-cdms-admin-area-seed.sql", records, metadata)
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


def write_cdms_admin_area_seed_sql(path: Path, records: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    """Write an idempotent CDMS seed for public.admin_area_levels/admin_areas.

    The normal png-address-data.sql export creates standalone import tables. CDMS
    already has the shared location backbone in public.admin_areas, so this export
    maps the PNG hierarchy into that schema while preserving source provenance in
    extra_json for later GIS boundary/GeoJSON linking.
    """
    admin_records = build_cdms_admin_area_records(records, metadata)
    columns = [
        "admin_code",
        "name",
        "level_code",
        "parent_code",
        "external_code",
        "source_system",
        "source_record_id",
        "source_level",
        "label",
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
        "geojson_level",
        "geojson_folder",
    ]

    lines = [
        "-- Papua New Guinea Administrative Area Seed for SDP CDMS",
        f"-- Year: {metadata['year']}",
        f"-- Generated at UTC: {metadata['generated_at_utc']}",
        "-- Target schema: public.admin_area_levels, public.admin_areas",
        "-- Hierarchy: COUNTRY -> REGION -> PROVINCE -> DISTRICT -> LLG -> WARD",
        "-- Notes:",
        "--   * Province codes use ISO 3166-2:PG where available.",
        "--   * District, LLG, and ward codes may be generated package codes.",
        "--   * Ward records are address/search records only unless geometry_available is true.",
        "--   * Boundary geometry is not embedded here; copy GeoJSON later and link by admin area code/provenance.",
        "",
        "BEGIN;",
        "",
        "INSERT INTO public.admin_area_levels (code, name, sort_order, description, is_active)",
        "VALUES",
        "('COUNTRY','Country',10,'Country level.',TRUE),",
        "('REGION','Region',20,'PNG region grouping level.',TRUE),",
        "('PROVINCE','Province',30,'Province level.',TRUE),",
        "('DISTRICT','District',40,'District level.',TRUE),",
        "('LLG','Local-Level Government',50,'LLG level.',TRUE),",
        "('WARD','Ward',60,'Ward level.',TRUE),",
        "('COMMUNITY','Community / Village / Settlement',70,'Community, village, or settlement level.',TRUE)",
        "ON CONFLICT (code) DO UPDATE SET",
        "    name = EXCLUDED.name,",
        "    sort_order = EXCLUDED.sort_order,",
        "    description = EXCLUDED.description,",
        "    is_active = EXCLUDED.is_active;",
        "",
        "CREATE TEMP TABLE tmp_png_admin_areas_seed (",
        "    admin_code TEXT NOT NULL,",
        "    name TEXT NOT NULL,",
        "    level_code TEXT NOT NULL,",
        "    parent_code TEXT NULL,",
        "    external_code TEXT NULL,",
        "    source_system TEXT NOT NULL,",
        "    source_record_id TEXT NULL,",
        "    source_level TEXT NULL,",
        "    label TEXT NULL,",
        "    region_code TEXT NULL,",
        "    region_name TEXT NULL,",
        "    province_code TEXT NULL,",
        "    province_name TEXT NULL,",
        "    district_code TEXT NULL,",
        "    district_name TEXT NULL,",
        "    llg_code TEXT NULL,",
        "    llg_name TEXT NULL,",
        "    ward_code TEXT NULL,",
        "    ward_name TEXT NULL,",
        "    ward_number INTEGER NULL,",
        "    code_system TEXT NULL,",
        "    standard_code TEXT NULL,",
        "    is_standard_code BOOLEAN NULL,",
        "    source_code TEXT NULL,",
        "    source_code_column TEXT NULL,",
        "    code_note TEXT NULL,",
        "    source_dataset TEXT NULL,",
        "    source_url TEXT NULL,",
        "    matched_to_map BOOLEAN NULL,",
        "    has_boundary BOOLEAN NULL,",
        "    geometry_available BOOLEAN NULL,",
        "    geojson_level TEXT NULL,",
        "    geojson_folder TEXT NULL",
        ") ON COMMIT DROP;",
        "",
    ]

    if admin_records:
        lines.append("INSERT INTO tmp_png_admin_areas_seed (")
        lines.append("    " + ", ".join(columns))
        lines.append(") VALUES")
        value_lines = []
        for record in admin_records:
            values = ", ".join(sql_literal(record.get(column)) for column in columns)
            value_lines.append(f"({values})")
        lines.append(",\n".join(value_lines) + ";")
        lines.append("")

    for level_code in ["COUNTRY", "REGION", "PROVINCE", "DISTRICT", "LLG", "WARD"]:
        lines.extend(admin_area_upsert_sql(level_code, metadata["year"]))

    lines.extend([
        "INSERT INTO public.app_settings (setting_scope, setting_key, setting_value, setting_json, description, is_secret, is_editable, is_active)",
        "VALUES (",
        "    'gis',",
        "    'png_admin_boundary_package',",
        "    " + sql_literal(f"png-json-maps/{metadata['year']}") + ",",
        "    " + sql_literal({
            "year": metadata["year"],
            "hierarchy": ["country", "region", "province", "district", "llg", "ward"],
            "geojson_root": f"png-json-maps/{metadata['year']}/geojson",
            "address_root": f"png-json-address/{metadata['year']}",
            "admin_area_match_key": "public.admin_areas.code",
            "note": "Copy the generated GeoJSON folder into the CDMS/GIS asset pipeline and join layers using admin area code/provenance metadata.",
        }) + ",",
        "    'Generated PNG administrative boundary/address package location for future GIS layer imports.',",
        "    FALSE, TRUE, TRUE",
        ")",
        "ON CONFLICT (setting_scope, setting_key) DO UPDATE SET",
        "    setting_value = EXCLUDED.setting_value,",
        "    setting_json = EXCLUDED.setting_json,",
        "    description = EXCLUDED.description,",
        "    is_secret = EXCLUDED.is_secret,",
        "    is_editable = EXCLUDED.is_editable,",
        "    is_active = EXCLUDED.is_active;",
        "",
        "COMMIT;",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def admin_area_upsert_sql(level_code: str, year: str) -> list[str]:
    return [
        f"-- Upsert {level_code.lower()} admin areas after their parent level exists.",
        "INSERT INTO public.admin_areas (",
        "    country_code, admin_area_level_id, parent_admin_area_id, code, name,",
        "    external_code, source_system, boundary_geojson, srid, extra_json, is_active",
        ")",
        "SELECT",
        "    'PNG',",
        "    lvl.admin_area_level_id,",
        "    parent.admin_area_id,",
        "    s.admin_code,",
        "    s.name,",
        "    s.external_code,",
        "    s.source_system,",
        "    NULL::jsonb,",
        "    4326,",
        "    jsonb_strip_nulls(jsonb_build_object(",
        "        'admin_standard_year', " + sql_literal(year) + ",",
        "        'source_record_id', s.source_record_id,",
        "        'source_level', s.source_level,",
        "        'source_code', s.source_code,",
        "        'source_code_column', s.source_code_column,",
        "        'original_code', s.external_code,",
        "        'code_system', s.code_system,",
        "        'standard_code', s.standard_code,",
        "        'is_standard_code', s.is_standard_code,",
        "        'label', s.label,",
        "        'region_code', s.region_code,",
        "        'region_name', s.region_name,",
        "        'province_code', s.province_code,",
        "        'province_name', s.province_name,",
        "        'district_code', s.district_code,",
        "        'district_name', s.district_name,",
        "        'llg_code', s.llg_code,",
        "        'llg_name', s.llg_name,",
        "        'ward_code', s.ward_code,",
        "        'ward_name', s.ward_name,",
        "        'ward_number', s.ward_number,",
        "        'code_note', s.code_note,",
        "        'source_dataset', s.source_dataset,",
        "        'source_url', s.source_url,",
        "        'matched_to_map', s.matched_to_map,",
        "        'has_boundary', s.has_boundary,",
        "        'geometry_available', s.geometry_available,",
        "        'geojson_level', s.geojson_level,",
        "        'geojson_folder', s.geojson_folder",
        "    )),",
        "    TRUE",
        "FROM tmp_png_admin_areas_seed s",
        "JOIN public.admin_area_levels lvl ON lvl.code = s.level_code",
        "LEFT JOIN public.admin_areas parent ON parent.country_code = 'PNG' AND parent.code = s.parent_code",
        f"WHERE s.level_code = {sql_literal(level_code)}",
        "ORDER BY s.name",
        "ON CONFLICT (country_code, admin_area_level_id, code) DO UPDATE SET",
        "    parent_admin_area_id = EXCLUDED.parent_admin_area_id,",
        "    name = EXCLUDED.name,",
        "    external_code = EXCLUDED.external_code,",
        "    source_system = EXCLUDED.source_system,",
        "    srid = EXCLUDED.srid,",
        "    extra_json = EXCLUDED.extra_json,",
        "    is_active = EXCLUDED.is_active;",
        "",
    ]


def build_cdms_admin_area_records(records: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw_records: list[dict[str, Any]] = [
        {
            "admin_code": "PNG",
            "name": "Papua New Guinea",
            "level_code": "COUNTRY",
            "parent_code": None,
            "external_code": "PNG",
            "source_system": "png-json-maps-generated",
            "source_record_id": "PNG-COUNTRY",
            "source_level": "country",
            "label": "Papua New Guinea",
            "code_system": "ISO 3166-1 alpha-3",
            "standard_code": "PNG",
            "is_standard_code": True,
            "has_boundary": True,
            "geometry_available": True,
            "geojson_level": "country",
            "geojson_folder": f"png-json-maps/{metadata['year']}/geojson/country",
        }
    ]

    for record in records:
        level = str(record.get("level", "")).lower()
        if level not in {"region", "province", "district", "llg", "ward"}:
            continue
        source_code = str(record.get("code", "")).strip()
        name = str(record.get("name", "")).strip()
        if not source_code or not name:
            continue
        raw_records.append(build_cdms_admin_area_record(record, source_code, metadata))

    duplicate_counts: dict[tuple[str, str], int] = {}
    for record in raw_records:
        key = (str(record["level_code"]), str(record["admin_code"]))
        duplicate_counts[key] = duplicate_counts.get(key, 0) + 1

    for record in raw_records:
        key = (str(record["level_code"]), str(record["admin_code"]))
        if duplicate_counts[key] <= 1:
            continue
        suffix = str(record.get("source_record_id", "")).replace("PNG-", "R")
        record["admin_code"] = f"{record['admin_code']}-{suffix}"

    code_map: dict[tuple[str, str], str] = {}
    for record in raw_records:
        external = str(record.get("external_code") or record.get("admin_code") or "")
        code_map[(str(record["level_code"]), external)] = str(record["admin_code"])

    for record in raw_records:
        parent_level = parent_level_code(str(record["level_code"]))
        parent_external = str(record.get("_parent_external_code") or "")
        if parent_level and parent_external:
            record["parent_code"] = code_map.get((parent_level, parent_external), parent_external)
        record.pop("_parent_external_code", None)

    order = {"COUNTRY": 10, "REGION": 20, "PROVINCE": 30, "DISTRICT": 40, "LLG": 50, "WARD": 60}
    return sorted(raw_records, key=lambda item: (order.get(str(item["level_code"]), 90), str(item.get("region_code", "")), str(item.get("province_code", "")), str(item.get("district_code", "")), str(item.get("llg_code", "")), int(item.get("ward_number") or 0), str(item["name"])))


def build_cdms_admin_area_record(record: dict[str, Any], source_code: str, metadata: dict[str, Any]) -> dict[str, Any]:
    level = str(record.get("level", "")).lower()
    level_code = "LLG" if level == "llg" else level.upper()
    geojson_folder_by_level = {
        "region": "regions",
        "province": "provinces",
        "district": "districts",
        "llg": "llgs",
        "ward": "wards",
    }
    return {
        "admin_code": source_code,
        "name": str(record.get("name", "")).strip(),
        "level_code": level_code,
        "parent_code": None,
        "_parent_external_code": parent_external_code(record, level),
        "external_code": source_code,
        "source_system": "png-json-maps-generated",
        "source_record_id": record.get("record_id"),
        "source_level": level,
        "label": record.get("label"),
        "region_code": record.get("region_code"),
        "region_name": record.get("region_name"),
        "province_code": record.get("province_code"),
        "province_name": record.get("province_name"),
        "district_code": record.get("district_code"),
        "district_name": record.get("district_name"),
        "llg_code": record.get("llg_code"),
        "llg_name": record.get("llg_name"),
        "ward_code": record.get("ward_code"),
        "ward_name": record.get("ward_name"),
        "ward_number": record.get("ward_number"),
        "code_system": record.get("code_system"),
        "standard_code": record.get("standard_code"),
        "is_standard_code": record.get("is_standard_code"),
        "source_code": record.get("source_code"),
        "source_code_column": record.get("source_code_column"),
        "code_note": record.get("code_note"),
        "source_dataset": record.get("source_dataset"),
        "source_url": record.get("source_url"),
        "matched_to_map": record.get("matched_to_map"),
        "has_boundary": record.get("has_boundary"),
        "geometry_available": record.get("geometry_available"),
        "geojson_level": level,
        "geojson_folder": f"png-json-maps/{metadata['year']}/geojson/{geojson_folder_by_level[level]}",
    }


def parent_external_code(record: dict[str, Any], level: str) -> str | None:
    if level == "region":
        return "PNG"
    if level == "province":
        return str(record.get("region_code") or "") or None
    if level == "district":
        return str(record.get("province_code") or "") or None
    if level == "llg":
        return str(record.get("district_code") or "") or None
    if level == "ward":
        return str(record.get("llg_code") or "") or None
    return None


def parent_level_code(level_code: str) -> str | None:
    return {
        "REGION": "COUNTRY",
        "PROVINCE": "REGION",
        "DISTRICT": "PROVINCE",
        "LLG": "DISTRICT",
        "WARD": "LLG",
    }.get(level_code)


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
        "- `png-cdms-admin-area-seed.sql` - CDMS-compatible seed for `public.admin_area_levels` and `public.admin_areas`.",
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
