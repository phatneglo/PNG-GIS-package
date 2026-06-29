#!/usr/bin/env python3
"""Build PNG address hierarchy/autocomplete JSON from generated map index files."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COUNTRY_CODE = "PNG"
COUNTRY_NAME = "Papua New Guinea"


def hierarchy_schema(ward_address_available: bool, ward_boundary_available: bool) -> list[dict[str, Any]]:
    return [
        {
            "level": "country",
            "label": "Country",
            "available_in_address_json": True,
            "available_as_boundary": True,
            "code_system_note": "ISO 3166-1 alpha-3.",
        },
        {
            "level": "region",
            "label": "Region",
            "available_in_address_json": True,
            "available_as_boundary": True,
            "code_system_note": "Package grouping used by PNG map/address package.",
        },
        {
            "level": "province",
            "label": "Province",
            "available_in_address_json": True,
            "available_as_boundary": True,
            "code_system_note": "Province codes use ISO 3166-2:PG where supplied by source shapeISO.",
        },
        {
            "level": "district",
            "label": "District",
            "available_in_address_json": True,
            "available_as_boundary": True,
            "code_system_note": "Generated package codes when source has no official code field.",
        },
        {
            "level": "llg",
            "label": "Local-level government",
            "available_in_address_json": True,
            "available_as_boundary": True,
            "code_system_note": "Generated package codes when source has no official code field.",
        },
        {
            "level": "ward",
            "label": "Ward",
            "available_in_address_json": ward_address_available,
            "available_as_boundary": ward_boundary_available,
            "code_system_note": "Official PNG hierarchy includes wards below LLG. Supplemental text ward records may exist even when ward boundary geometry is unavailable.",
        },
        {
            "level": "census_unit",
            "label": "Census unit",
            "available_in_address_json": False,
            "available_as_boundary": False,
            "code_system_note": "Used for census purposes below ward; not included in the current source data.",
        },
    ]


def by_code(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("code", "")): item for item in items if item.get("code")}


def norm_name(value: str) -> str:
    value = value.lower().replace("&", "and")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\b(autonomous region of|province|district|rural|urban|local level government|llg|region)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slug_code(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value or "UNKNOWN"


def compact_item(item: dict[str, Any], level: str, parents: dict[str, str] | None = None) -> dict[str, Any]:
    code_meta = code_metadata(item, level)
    result = {
        "code": str(item.get("code", "")),
        "name": str(item.get("name", "")),
        "level": level,
        **code_meta,
    }
    if parents:
        result.update({k: v for k, v in parents.items() if v})
    return result


def flat_item(item: dict[str, Any], level: str, parents: dict[str, str]) -> dict[str, Any]:
    code_meta = code_metadata(item, level)
    names = [
        item.get("name"),
        parents.get("llg_name"),
        parents.get("district_name"),
        parents.get("province_name"),
        parents.get("region_name"),
        COUNTRY_NAME,
    ]
    path = [str(name) for name in names if name and str(name) != str(item.get("name"))]
    label_parts = [str(item.get("name", "")), *path]
    result = {
        "code": str(item.get("code", "")),
        "name": str(item.get("name", "")),
        "level": level,
        "label": ", ".join([part for part in label_parts if part]),
        "path": path,
        "country_code": COUNTRY_CODE,
        "country_name": COUNTRY_NAME,
        **code_meta,
        **{k: v for k, v in parents.items() if v},
    }
    if level == "llg":
        result.update({
            "next_level": "ward",
            "child_level": "ward",
            "child_records_available": False,
            "child_record_note": "PNG hierarchy has wards below LLG, but no ward records are available in the current generated source.",
        })
    return result


def code_metadata(item: dict[str, Any], level: str) -> dict[str, Any]:
    code = str(item.get("code", ""))
    source_code = str(item.get("source_code", "") or "")
    source_code_column = str(item.get("source_code_column", "") or "")

    if level == "country":
        return {
            "code_system": "ISO 3166-1 alpha-3",
            "standard_code": COUNTRY_CODE,
            "is_standard_code": True,
            "source_code": source_code,
            "source_code_column": source_code_column,
        }

    if level == "province" and code.startswith("PG-"):
        return {
            "code_system": "ISO 3166-2:PG",
            "standard_code": code,
            "is_standard_code": True,
            "source_code": source_code or code,
            "source_code_column": source_code_column or "shapeISO",
        }

    if source_code:
        return {
            "code_system": f"source:{source_code_column or 'unknown'}",
            "standard_code": source_code,
            "is_standard_code": True,
            "source_code": source_code,
            "source_code_column": source_code_column,
        }

    return {
        "code_system": "png-json-maps-generated",
        "standard_code": "",
        "is_standard_code": False,
        "source_code": source_code,
        "source_code_column": source_code_column,
        "code_note": "Generated stable package code; not a verified official PSGC-style registry code.",
    }


def build_supplemental_geolist_wards(index: dict[str, Any]) -> dict[str, Any]:
    source_path = Path("data-sources/papua-new-guinea-geolist/GeoList.json")
    if not source_path.exists():
        return {
            "records": [],
            "matched_ward_count": 0,
            "unmatched_ward_count": 0,
            "unmatched_groups": [],
            "sources": [],
        }

    geolist = json.loads(source_path.read_text(encoding="utf-8"))
    llg_matches = build_llg_match_index(index)
    records: list[dict[str, Any]] = []
    unmatched_groups: list[dict[str, Any]] = []
    matched_ward_count = 0
    unmatched_ward_count = 0

    for province in geolist.get("provinces", []):
        province_name = str(province.get("province", ""))
        for district in province.get("districts", []):
            district_name = str(district.get("district", ""))
            for llg in district.get("llgs", []):
                llg_name = str(llg.get("llg", ""))
                wards = llg.get("wards", [])
                match = find_llg_match(llg_matches, province_name, district_name, llg_name)
                matched_to_map = match is not None

                if not matched_to_map:
                    unmatched_groups.append({
                        "province_name": province_name,
                        "district_name": district_name,
                        "llg_name": llg_name,
                        "ward_count": len(wards),
                    })

                for index_no, ward in enumerate(wards, start=1):
                    ward_name = str(ward.get("ward", "")).strip()
                    ward_number = ward.get("wardNumber", 0)
                    try:
                        ward_number_int = int(ward_number)
                    except (TypeError, ValueError):
                        ward_number_int = 0
                    number_for_code = ward_number_int if ward_number_int > 0 else index_no

                    if match:
                        code = f"{match['code']}-W{number_for_code:03d}"
                        parents = {
                            "region_code": str(match.get("region_code", "")),
                            "region_name": str(match.get("region_name", "")),
                            "province_code": str(match.get("province_code", "")),
                            "province_name": str(match.get("province_name", "")),
                            "district_code": str(match.get("district_code", "")),
                            "district_name": str(match.get("district_name", "")),
                            "llg_code": str(match.get("code", "")),
                            "llg_name": str(match.get("name", "")),
                        }
                        matched_ward_count += 1
                    else:
                        code = "GEOLIST-" + "-".join([
                            slug_code(province_name),
                            slug_code(district_name),
                            slug_code(llg_name),
                            f"W{number_for_code:03d}",
                        ])
                        parents = {
                            "source_province_name": province_name,
                            "source_district_name": district_name,
                            "source_llg_name": llg_name,
                            "llg_name": llg_name,
                        }
                        unmatched_ward_count += 1

                    label_parts = [
                        ward_name,
                        parents.get("llg_name") or llg_name,
                        parents.get("district_name") or district_name,
                        parents.get("province_name") or province_name,
                        parents.get("region_name"),
                        COUNTRY_NAME,
                    ]
                    records.append({
                        "code": code,
                        "name": ward_name,
                        "level": "ward",
                        "label": ", ".join([str(part) for part in label_parts if part]),
                        "path": [str(part) for part in label_parts[1:] if part],
                        "country_code": COUNTRY_CODE,
                        "country_name": COUNTRY_NAME,
                        "ward_code": code,
                        "ward_name": ward_name,
                        "ward_number": ward_number_int,
                        "code_system": "papua-new-guinea-geolist-address-generated",
                        "standard_code": "",
                        "is_standard_code": False,
                        "source_code": "",
                        "source_code_column": "wardNumber",
                        "code_note": "Address-only generated ward code from supplemental GeoList text source; no ward boundary geometry is included.",
                        "source_dataset": "wilfred-wulbou/papua-new-guinea-geolist",
                        "source_url": "https://github.com/wilfred-wulbou/papua-new-guinea-geolist",
                        "matched_to_map": matched_to_map,
                        "has_boundary": False,
                        "geometry_available": False,
                        **parents,
                    })

    return {
        "records": records,
        "matched_ward_count": matched_ward_count,
        "unmatched_ward_count": unmatched_ward_count,
        "unmatched_groups": unmatched_groups,
        "sources": [
            {
                "name": "papua-new-guinea-geolist",
                "url": "https://github.com/wilfred-wulbou/papua-new-guinea-geolist",
                "license": "MIT",
                "usage": "Supplemental text-only ward names for address autocomplete. No geometry.",
                "local_path": str(source_path),
            }
        ],
    }


def build_llg_match_index(index: dict[str, Any]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    matches: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for llg in index.get("llgs", []):
        province = norm_name(str(llg.get("province_name", "")))
        district = norm_name(str(llg.get("district_name", "")))
        names = {
            norm_name(str(llg.get("name", ""))),
            norm_name(str(llg.get("name", "")).replace("/", " ")),
            norm_name(str(llg.get("name", "")).replace("-", " ")),
        }
        for name in names:
            for key in [(province, district, name), (province, "", name), ("", "", name)]:
                matches.setdefault(key, []).append(llg)
    return matches


def find_llg_match(matches: dict[tuple[str, str, str], list[dict[str, Any]]], province: str, district: str, llg: str) -> dict[str, Any] | None:
    province_key = norm_name(province)
    district_key = norm_name(district)
    llg_key = norm_name(llg)
    for key in [(province_key, district_key, llg_key), (province_key, "", llg_key), ("", "", llg_key)]:
        candidates = matches.get(key, [])
        unique = {str(candidate.get("code", "")): candidate for candidate in candidates}
        if len(unique) == 1:
            return next(iter(unique.values()))
    return None


def build(index: dict[str, Any], year: str) -> dict[str, Any]:
    regions = index.get("regions", [])
    provinces = index.get("provinces", [])
    districts = index.get("districts", [])
    llgs = index.get("llgs", [])
    wards = index.get("wards", [])
    boundary_wards_available = len(wards) > 0

    region_lookup = by_code(regions)
    province_lookup = by_code(provinces)
    district_lookup = by_code(districts)
    llg_lookup = by_code(llgs)

    flat: list[dict[str, Any]] = []
    hierarchy_regions = []
    llg_nodes_by_code: dict[str, dict[str, Any]] = {}

    for region in sorted(regions, key=lambda item: str(item.get("name", ""))):
        region_code = str(region.get("code", ""))
        region_node = compact_item(region, "region")
        region_node["provinces"] = []
        flat.append(flat_item(region, "region", {"region_code": region_code, "region_name": str(region.get("name", ""))}))

        region_provinces = [
            item for item in provinces
            if str(item.get("region_code", "")) == region_code
        ]
        for province in sorted(region_provinces, key=lambda item: str(item.get("name", ""))):
            province_code = str(province.get("code", ""))
            province_parents = {
                "region_code": region_code,
                "region_name": str(region.get("name", "")),
                "province_code": province_code,
                "province_name": str(province.get("name", "")),
            }
            province_node = compact_item(province, "province", province_parents)
            province_node["districts"] = []
            flat.append(flat_item(province, "province", province_parents))

            province_districts = [
                item for item in districts
                if str(item.get("province_code", item.get("parent_code", ""))) == province_code
            ]
            for district in sorted(province_districts, key=lambda item: str(item.get("name", ""))):
                district_code = str(district.get("code", ""))
                district_parents = {
                    **province_parents,
                    "district_code": district_code,
                    "district_name": str(district.get("name", "")),
                }
                district_node = compact_item(district, "district", district_parents)
                district_node["llgs"] = []
                flat.append(flat_item(district, "district", district_parents))

                district_llgs = [
                    item for item in llgs
                    if str(item.get("district_code", item.get("parent_code", ""))) == district_code
                ]
                for llg in sorted(district_llgs, key=lambda item: str(item.get("name", ""))):
                    llg_code = str(llg.get("code", ""))
                    llg_parents = {
                        **district_parents,
                        "llg_code": llg_code,
                        "llg_name": str(llg.get("name", "")),
                    }
                    llg_node = compact_item(llg, "llg", llg_parents)
                    llg_node["wards"] = []
                    llg_node["wards_available"] = False
                    llg_node["ward_boundaries_available"] = False
                    llg_node["child_level"] = "ward"
                    llg_node["child_record_note"] = "PNG hierarchy has wards below LLG. Supplemental ward address records may be available even when ward boundaries are not."
                    llg_nodes_by_code[llg_code] = llg_node
                    flat.append(flat_item(llg, "llg", llg_parents))

                    llg_wards = [
                        item for item in wards
                        if str(item.get("llg_code", item.get("parent_code", ""))) == llg_code
                    ]
                    for ward in sorted(llg_wards, key=lambda item: str(item.get("name", ""))):
                        ward_parents = {
                            **llg_parents,
                            "ward_code": str(ward.get("code", "")),
                            "ward_name": str(ward.get("name", "")),
                        }
                        ward_node = compact_item(ward, "ward", ward_parents)
                        llg_node["wards"].append(ward_node)
                        flat.append(flat_item(ward, "ward", ward_parents))

                    if llg_node["wards"]:
                        llg_node["wards_available"] = True
                        llg_node["ward_boundaries_available"] = True
                        llg_node["child_record_note"] = ""

                    district_node["llgs"].append(llg_node)
                province_node["districts"].append(district_node)
            region_node["provinces"].append(province_node)
        hierarchy_regions.append(region_node)

    # Keep orphan records visible if a future source has incomplete parent fields.
    known_codes = {item["code"] for item in flat}
    for level, items, lookups in [
        ("province", provinces, province_lookup),
        ("district", districts, district_lookup),
        ("llg", llgs, llg_lookup),
        ("ward", wards, {}),
    ]:
        for item in items:
            code = str(item.get("code", ""))
            if code and code not in known_codes:
                flat.append(flat_item(item, level, {
                    "region_code": str(item.get("region_code", "")),
                    "region_name": str(item.get("region_name", "")),
                    "province_code": str(item.get("province_code", "")),
                    "province_name": str(item.get("province_name", "")),
                    "district_code": str(item.get("district_code", "")),
                    "district_name": str(item.get("district_name", "")),
                    "llg_code": str(item.get("llg_code", "")),
                    "llg_name": str(item.get("llg_name", "")),
                }))
                known_codes.add(code)

    supplemental = build_supplemental_geolist_wards(index)
    for ward_record in supplemental["records"]:
        flat.append(ward_record)
        llg_code = str(ward_record.get("llg_code", ""))
        if llg_code in llg_nodes_by_code:
            llg_nodes_by_code[llg_code]["wards"].append(compact_item(ward_record, "ward", {
                "region_code": str(ward_record.get("region_code", "")),
                "region_name": str(ward_record.get("region_name", "")),
                "province_code": str(ward_record.get("province_code", "")),
                "province_name": str(ward_record.get("province_name", "")),
                "district_code": str(ward_record.get("district_code", "")),
                "district_name": str(ward_record.get("district_name", "")),
                "llg_code": llg_code,
                "llg_name": str(ward_record.get("llg_name", "")),
            }))
            llg_nodes_by_code[llg_code]["wards_available"] = True
            llg_nodes_by_code[llg_code]["child_records_available"] = True
            llg_nodes_by_code[llg_code]["child_record_note"] = "Ward address records are available from supplemental text source; ward boundary geometry is not available."

    ward_address_available = len(wards) + supplemental["matched_ward_count"] + supplemental["unmatched_ward_count"] > 0

    stats = {
        "regions": len(regions),
        "provinces": len(provinces),
        "districts": len(districts),
        "llgs": len(llgs),
        "wards": len(wards) + supplemental["matched_ward_count"] + supplemental["unmatched_ward_count"],
        "ward_boundaries": len(wards),
        "supplemental_ward_records": supplemental["matched_ward_count"] + supplemental["unmatched_ward_count"],
        "supplemental_ward_records_matched_to_map_llg": supplemental["matched_ward_count"],
        "supplemental_ward_records_unmatched_to_map_llg": supplemental["unmatched_ward_count"],
        "flat_records": len(flat),
    }

    return {
        "year": str(year),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "country": {
            "code": COUNTRY_CODE,
            "name": COUNTRY_NAME,
            "regions": hierarchy_regions,
        },
        "administrative_hierarchy": hierarchy_schema(ward_address_available, boundary_wards_available),
        "unavailable_levels": [
            {
                "level": "ward",
                "parent_level": "llg",
                "reason": "The current generated boundary source has no ADM4/ward geometry. Ward address records may be supplied from supplemental text sources, but LLG is the deepest available boundary level.",
            }
        ] if not boundary_wards_available else [],
        "supplemental_sources": supplemental["sources"],
        "supplemental_unmatched_ward_groups": supplemental["unmatched_groups"],
        "flat": flat,
        "stats": stats,
        "notes": [
            "PNG address hierarchy follows country -> region -> province -> district -> LLG -> ward when ward data exists.",
            "Current gbOpen output may stop at LLG if ADM4/ward geometry is unavailable.",
            "Use flat records for autocomplete; use hierarchy for cascading address selectors.",
        ],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps-root", default="./png-json-maps", help="Generated png-json-maps root")
    parser.add_argument("--out", default="./png-json-address", help="Output root for address JSON")
    parser.add_argument("--year", default="", help="Optional single year to build")
    args = parser.parse_args()

    maps_root = Path(args.maps_root)
    out_root = Path(args.out)
    year_dirs = [maps_root / args.year] if args.year else sorted([p for p in maps_root.iterdir() if p.is_dir() and p.name.isdigit()])

    built = 0
    for year_dir in year_dirs:
        index_path = year_dir / "index.json"
        if not index_path.exists():
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        data = build(index, year_dir.name)
        out_dir = out_root / year_dir.name
        hierarchy = {k: v for k, v in data.items() if k != "flat"}
        flat = {
            "year": data["year"],
            "generated_at_utc": data["generated_at_utc"],
            "country": {"code": COUNTRY_CODE, "name": COUNTRY_NAME},
            "records": data["flat"],
            "stats": data["stats"],
        }
        write_json(out_dir / "address-hierarchy.json", hierarchy)
        write_json(out_dir / "address-flat.json", flat)
        built += 1
        print(f"Wrote {out_dir} ({data['stats']['flat_records']} address records).")

    if built == 0:
        raise SystemExit("No year index files found.")


if __name__ == "__main__":
    main()
