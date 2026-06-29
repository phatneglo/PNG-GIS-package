#!/usr/bin/env python3
"""
png_json_maps_auto.py

One-command automatic generator for a PNG GeoJSON/TopoJSON map repository.
It downloads open boundary data automatically, normalizes the hierarchy, creates
parent-child drilldown files, and converts them to TopoJSON using mapshaper.

Primary automatic source:
  geoBoundaries API: https://www.geoboundaries.org/api/current/gbOpen/PNG/ADM{N}/

Generated hierarchy:
  country -> regions -> provinces -> districts -> llgs -> wards (if ADM4 exists)

Notes:
  - PNG does not use City/Municipality like the Philippines. The closest layer is LLG.
  - Ward geometry may not be available from every open source. If ADM4 cannot be
    downloaded, the script skips wards but keeps the folder structure ready.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import geopandas as gpd
from shapely.geometry import mapping

COUNTRY_CODE = "PNG"
COUNTRY_NAME = "Papua New Guinea"

GEOB_URL = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{adm}/"

RESOLUTIONS = {
    # mapshaper: retain this approximate percent of points, while keeping shapes
    "hires": "30%",
    "medres": "10%",
    "lowres": "2%",
}

PNG_PROVINCE_ISO = {
    "autonomous region of bougainville": "PG-NSB",
    "bougainville": "PG-NSB",
    "north solomons": "PG-NSB",
    "central": "PG-CPM",
    "central province": "PG-CPM",
    "chimbu": "PG-CPK",
    "simbu": "PG-CPK",
    "east new britain": "PG-EBR",
    "east sepik": "PG-ESW",
    "eastern highlands": "PG-EHG",
    "enga": "PG-EPW",
    "gulf": "PG-GPK",
    "hela": "PG-HLA",
    "jiwaka": "PG-JWK",
    "madang": "PG-MPM",
    "manus": "PG-MRL",
    "milne bay": "PG-MBA",
    "morobe": "PG-MPL",
    "national capital district": "PG-NCD",
    "ncd": "PG-NCD",
    "new ireland": "PG-NIK",
    "northern": "PG-NPP",
    "oro": "PG-NPP",
    "southern highlands": "PG-SHM",
    "west new britain": "PG-WBK",
    "west sepik": "PG-SAN",
    "sandaun": "PG-SAN",
    "western": "PG-WPD",
    "fly": "PG-WPD",
    "western highlands": "PG-WHM",
}

REGION_BY_PROVINCE = {
    # Highlands
    "hela": ("HIGHLANDS", "Highlands Region"),
    "jiwaka": ("HIGHLANDS", "Highlands Region"),
    "simbu": ("HIGHLANDS", "Highlands Region"),
    "chimbu": ("HIGHLANDS", "Highlands Region"),
    "eastern highlands": ("HIGHLANDS", "Highlands Region"),
    "enga": ("HIGHLANDS", "Highlands Region"),
    "southern highlands": ("HIGHLANDS", "Highlands Region"),
    "western highlands": ("HIGHLANDS", "Highlands Region"),
    # Islands
    "east new britain": ("ISLANDS", "Islands Region"),
    "manus": ("ISLANDS", "Islands Region"),
    "new ireland": ("ISLANDS", "Islands Region"),
    "bougainville": ("ISLANDS", "Islands Region"),
    "autonomous region of bougainville": ("ISLANDS", "Islands Region"),
    "north solomons": ("ISLANDS", "Islands Region"),
    "west new britain": ("ISLANDS", "Islands Region"),
    # Momase
    "east sepik": ("MOMASE", "Momase Region"),
    "madang": ("MOMASE", "Momase Region"),
    "morobe": ("MOMASE", "Momase Region"),
    "west sepik": ("MOMASE", "Momase Region"),
    "sandaun": ("MOMASE", "Momase Region"),
    # Southern
    "central": ("SOUTHERN", "Southern Region"),
    "central province": ("SOUTHERN", "Southern Region"),
    "gulf": ("SOUTHERN", "Southern Region"),
    "milne bay": ("SOUTHERN", "Southern Region"),
    "northern": ("SOUTHERN", "Southern Region"),
    "oro": ("SOUTHERN", "Southern Region"),
    "western": ("SOUTHERN", "Southern Region"),
    "fly": ("SOUTHERN", "Southern Region"),
    "national capital district": ("SOUTHERN", "Southern Region"),
    "ncd": ("SOUTHERN", "Southern Region"),
}

LEVELS = {
    0: {"key": "country", "folder": "country", "name": "country"},
    1: {"key": "province", "folder": "provinces", "name": "province"},
    2: {"key": "district", "folder": "districts", "name": "district"},
    3: {"key": "llg", "folder": "llgs", "name": "llg"},
    4: {"key": "ward", "folder": "wards", "name": "ward"},
}

@dataclass
class SourceMeta:
    level: int
    api_url: str
    geojson_url: str
    boundary_id: str = ""
    boundary_source: str = ""
    boundary_license: str = ""
    boundary_year: str = ""
    downloaded_to: str = ""


def log(msg: str) -> None:
    print(f"[PNG maps] {msg}", flush=True)


def slug(value: object, max_len: int = 80) -> str:
    txt = str(value or "").strip().upper()
    txt = re.sub(r"[^A-Z0-9]+", "-", txt)
    txt = re.sub(r"-+", "-", txt).strip("-")
    return (txt[:max_len] or "UNKNOWN")


def clean_name(value: object) -> str:
    txt = str(value or "").strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt


def normalize_lookup_name(value: object) -> str:
    txt = clean_name(value).lower()
    txt = re.sub(r"\bprovince\b", "", txt)
    txt = re.sub(r"\bdistrict\b", "", txt)
    txt = re.sub(r"\bllg\b", "", txt)
    txt = re.sub(r"\blocal level government\b", "", txt)
    txt = re.sub(r"\brural\b", "rural", txt)
    txt = re.sub(r"\burban\b", "urban", txt)
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def run(cmd: List[str], cwd: Optional[Path] = None, allow_fail: bool = False) -> subprocess.CompletedProcess:
    log("RUN " + " ".join(str(x) for x in cmd))
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.stdout.strip():
        print(p.stdout.strip())
    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(f"Command failed with exit code {p.returncode}: {' '.join(cmd)}")
    return p


def check_mapshaper() -> str:
    exe = shutil.which("mapshaper") or shutil.which("mapshaper.cmd")
    if not exe:
        raise RuntimeError("mapshaper not found. Install with: npm install -g mapshaper")
    return exe


def request_json(url: str, timeout: int = 60) -> dict:
    headers = {"User-Agent": "png-json-maps-generator/1.0 (+system-design)"}
    last_err = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch JSON: {url}\n{last_err}")


def download_file(url: str, target: Path, timeout: int = 180) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "png-json-maps-generator/1.0 (+system-design)"}
    last_err = None
    for attempt in range(1, 4):
        try:
            with requests.get(url, headers=headers, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                with target.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if target.stat().st_size < 100:
                raise RuntimeError(f"Downloaded file is too small: {target}")
            return
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to download: {url}\n{last_err}")


def download_geoboundaries(level: int, source_dir: Path) -> Optional[SourceMeta]:
    adm = f"ADM{level}"
    api_url = GEOB_URL.format(iso=COUNTRY_CODE, adm=adm)
    try:
        meta = request_json(api_url)
    except FileNotFoundError:
        log(f"No geoBoundaries {adm} layer found. Skipping.")
        return None
    except Exception as e:
        log(f"Could not fetch geoBoundaries {adm}: {e}")
        return None

    gj_url = meta.get("gjDownloadURL") or meta.get("simplifiedGeometryGeoJSON")
    if not gj_url:
        log(f"geoBoundaries {adm} did not return a GeoJSON download URL. Skipping.")
        return None

    target = source_dir / "geoboundaries" / f"PNG_{adm}.geojson"
    log(f"Downloading {adm} from geoBoundaries: {gj_url}")
    download_file(gj_url, target)

    return SourceMeta(
        level=level,
        api_url=api_url,
        geojson_url=gj_url,
        boundary_id=meta.get("boundaryID", ""),
        boundary_source=meta.get("boundarySource", ""),
        boundary_license=meta.get("boundaryLicense", ""),
        boundary_year=meta.get("boundaryYearRepresented", ""),
        downloaded_to=str(target),
    )


def read_layer(path: Path) -> gpd.GeoDataFrame:
    log(f"Reading {path}")
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise RuntimeError(f"Layer is empty: {path}")
    if gdf.crs is None:
        log(f"CRS missing for {path}; assuming EPSG:4326")
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    gdf = gdf[gdf.geometry.notna()].copy()
    # Fix simple geometry issues.
    try:
        gdf["geometry"] = gdf.geometry.make_valid()
    except Exception:
        gdf["geometry"] = gdf.geometry.buffer(0)
    return gdf


def pick_col(gdf: gpd.GeoDataFrame, candidates: Iterable[str]) -> Optional[str]:
    lower = {str(c).lower(): c for c in gdf.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def detect_name_col(gdf: gpd.GeoDataFrame, level: int) -> Optional[str]:
    common = [
        f"ADM{level}_EN", f"ADM{level}_NAME", f"ADM{level}_NA", f"NAME_{level}", f"NAME{level}",
        "shapeName", "shapeName_en", "name", "NAME", "boundaryName",
    ]
    return pick_col(gdf, common)


def detect_code_col(gdf: gpd.GeoDataFrame, level: int) -> Optional[str]:
    common = [
        f"ADM{level}_PCODE", f"ADM{level}_CODE", f"ADM{level}_ID", f"GID_{level}", f"ID_{level}",
        "shapeISO", "shapeID", "code", "CODE", "id", "ID",
    ]
    return pick_col(gdf, common)


def detect_parent_col(gdf: gpd.GeoDataFrame, parent_level: int) -> Optional[str]:
    common = [
        f"ADM{parent_level}_PCODE", f"ADM{parent_level}_CODE", f"ADM{parent_level}_ID", f"GID_{parent_level}",
        f"PARENT_ADM{parent_level}", "parent_code", "PARENT", "parent",
    ]
    return pick_col(gdf, common)


def province_iso_from_name(name: str, fallback_index: int) -> str:
    key = normalize_lookup_name(name)
    if key in PNG_PROVINCE_ISO:
        return PNG_PROVINCE_ISO[key]
    # Try contains match for names like "West Sepik Province (Sandaun)".
    for k, v in PNG_PROVINCE_ISO.items():
        if k in key or key in k:
            return v
    return f"PNG-P{fallback_index:02d}"


def region_from_province(name: str) -> Tuple[str, str]:
    key = normalize_lookup_name(name)
    if key in REGION_BY_PROVINCE:
        return REGION_BY_PROVINCE[key]
    for k, v in REGION_BY_PROVINCE.items():
        if k in key or key in k:
            return v
    return "UNMAPPED", "Unmapped Region"


def normalize_layer(gdf: gpd.GeoDataFrame, level: int) -> gpd.GeoDataFrame:
    name_col = detect_name_col(gdf, level)
    code_col = detect_code_col(gdf, level)
    if not name_col:
        raise RuntimeError(f"Could not detect name column for ADM{level}. Columns: {list(gdf.columns)}")

    out = gdf.copy()
    out["name"] = out[name_col].map(clean_name)
    out["source_name_column"] = name_col
    out["source_code_column"] = code_col or ""
    out["source_code"] = out[code_col].astype(str) if code_col else ""
    out["admin_level"] = level
    out["admin_level_name"] = LEVELS[level]["name"]
    out["country_code"] = COUNTRY_CODE
    out["country_name"] = COUNTRY_NAME

    if level == 0:
        out["code"] = COUNTRY_CODE
        out["parent_code"] = ""
    elif level == 1:
        codes = []
        for idx, nm in enumerate(out["name"].tolist(), start=1):
            codes.append(province_iso_from_name(nm, idx))
        # If duplicates appear because names are unusual, make them unique.
        seen = {}
        fixed = []
        for c in codes:
            seen[c] = seen.get(c, 0) + 1
            fixed.append(c if seen[c] == 1 else f"{c}-{seen[c]}")
        out["code"] = fixed
        out["province_code"] = out["code"]
        out["province_name"] = out["name"]
        out["parent_code"] = COUNTRY_CODE
        region_data = out["name"].map(region_from_province)
        out["region_code"] = [x[0] for x in region_data]
        out["region_name"] = [x[1] for x in region_data]
    else:
        # Parent code will be filled later by direct field or spatial assignment.
        # Use source codes if available, else temporary code. After parent assignment,
        # we regenerate clean hierarchy codes per parent.
        out["code"] = out["source_code"].where(out["source_code"].astype(str).str.strip() != "", "")
        out["parent_code"] = ""

    return out


def assign_parent_by_field(child: gpd.GeoDataFrame, child_level: int, parent: gpd.GeoDataFrame, parent_level: int) -> gpd.GeoDataFrame:
    parent_col = detect_parent_col(child, parent_level)
    if not parent_col:
        return child
    mapping_by_source = {}
    for _, row in parent.iterrows():
        for col in ["source_code", "code"]:
            val = str(row.get(col, "")).strip()
            if val:
                mapping_by_source[val] = row["code"]
    if not mapping_by_source:
        return child
    raw = child[parent_col].astype(str).str.strip()
    matched = raw.map(mapping_by_source)
    if matched.notna().sum() > 0:
        child = child.copy()
        child["parent_code"] = matched.fillna(child["parent_code"])
        log(f"ADM{child_level}: assigned {matched.notna().sum()} parent codes from field {parent_col}")
    return child


def assign_parent_spatial(child: gpd.GeoDataFrame, child_level: int, parent: gpd.GeoDataFrame, parent_level: int) -> gpd.GeoDataFrame:
    missing = child["parent_code"].astype(str).str.strip() == ""
    if not missing.any():
        return child
    log(f"ADM{child_level}: spatially assigning parent ADM{parent_level} for {missing.sum()} features")
    # Use representative points to reduce edge-case centroid-outside-polygon failures.
    pts = child.loc[missing, ["name", "geometry"]].copy()
    pts["geometry"] = pts.geometry.representative_point()
    parent_min = parent[["code", "name", "geometry"]].rename(columns={"code": "_parent_code", "name": "_parent_name"})
    joined = gpd.sjoin(pts, parent_min, how="left", predicate="within")
    child = child.copy()
    for idx, row in joined.iterrows():
        pc = row.get("_parent_code")
        if isinstance(pc, str) and pc.strip():
            child.at[idx, "parent_code"] = pc
    still_missing = (child["parent_code"].astype(str).str.strip() == "").sum()
    if still_missing:
        log(f"WARNING: ADM{child_level}: {still_missing} features still have no parent after spatial join")
    return child


def generate_child_codes(child: gpd.GeoDataFrame, level: int) -> gpd.GeoDataFrame:
    key = LEVELS[level]["key"]
    child = child.copy()
    if level <= 1:
        return child
    new_codes = []
    counters: Dict[str, int] = {}
    for _, row in child.sort_values(["parent_code", "name"]).iterrows():
        parent_code = str(row.get("parent_code", "") or f"PNG-ADM{level-1}")
        source_code = str(row.get("source_code", "") or "").strip()
        if source_code and re.match(r"^[A-Za-z0-9_.:-]{3,}$", source_code) and source_code.upper() not in {"NONE", "NAN"}:
            code = slug(source_code, 50)
        else:
            counters[parent_code] = counters.get(parent_code, 0) + 1
            prefix = {2: "D", 3: "L", 4: "W"}.get(level, f"A{level}")
            code = f"{parent_code}-{prefix}{counters[parent_code]:03d}"
        new_codes.append((row.name, code))
    for idx, code in new_codes:
        child.at[idx, "code"] = code
    child[f"{key}_code"] = child["code"]
    child[f"{key}_name"] = child["name"]
    return child


def enrich_context(layers: Dict[int, gpd.GeoDataFrame]) -> Dict[int, gpd.GeoDataFrame]:
    # Add parent relations and codes.
    if 1 not in layers:
        raise RuntimeError("ADM1/province layer is required. geoBoundaries did not provide it.")

    # Create province context.
    adm1 = layers[1].copy()
    layers[1] = adm1

    for level in [2, 3, 4]:
        if level not in layers or level - 1 not in layers:
            continue
        child = layers[level]
        parent = layers[level - 1]
        child = assign_parent_by_field(child, level, parent, level - 1)
        child = assign_parent_spatial(child, level, parent, level - 1)
        child = generate_child_codes(child, level)
        layers[level] = child

    # Bring parent names/codes downward for easier filtering and frontend.
    if 2 in layers:
        p = layers[1][["code", "name", "region_code", "region_name"]].rename(columns={"code": "parent_code", "name": "province_name"})
        layers[2] = layers[2].merge(p, on="parent_code", how="left")
        layers[2]["province_code"] = layers[2]["parent_code"]
        layers[2]["district_code"] = layers[2]["code"]
        layers[2]["district_name"] = layers[2]["name"]
    if 3 in layers:
        p = layers[2][["code", "name", "province_code", "province_name", "region_code", "region_name"]].rename(columns={"code": "parent_code", "name": "district_name"})
        layers[3] = layers[3].merge(p, on="parent_code", how="left")
        layers[3]["district_code"] = layers[3]["parent_code"]
        layers[3]["llg_code"] = layers[3]["code"]
        layers[3]["llg_name"] = layers[3]["name"]
    if 4 in layers:
        p = layers[3][["code", "name", "district_code", "district_name", "province_code", "province_name", "region_code", "region_name"]].rename(columns={"code": "parent_code", "name": "llg_name"})
        layers[4] = layers[4].merge(p, on="parent_code", how="left")
        layers[4]["llg_code"] = layers[4]["parent_code"]
        layers[4]["ward_code"] = layers[4]["code"]
        layers[4]["ward_name"] = layers[4]["name"]

    return layers


def create_country_layer(layers: Dict[int, gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    if 0 in layers:
        country = layers[0].copy()
        country["name"] = COUNTRY_NAME
        country["code"] = COUNTRY_CODE
        country["parent_code"] = ""
        return country[["code", "name", "parent_code", "admin_level", "admin_level_name", "country_code", "country_name", "geometry"]]
    adm1 = layers[1]
    country = adm1.dissolve().reset_index(drop=True)
    country["code"] = COUNTRY_CODE
    country["name"] = COUNTRY_NAME
    country["parent_code"] = ""
    country["admin_level"] = 0
    country["admin_level_name"] = "country"
    country["country_code"] = COUNTRY_CODE
    country["country_name"] = COUNTRY_NAME
    return country[["code", "name", "parent_code", "admin_level", "admin_level_name", "country_code", "country_name", "geometry"]]


def create_region_layer(adm1: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    required = adm1[adm1["region_code"].astype(str).str.strip() != ""].copy()
    regions = required.dissolve(by=["region_code", "region_name"], as_index=False)
    regions["code"] = regions["region_code"]
    regions["name"] = regions["region_name"]
    regions["parent_code"] = COUNTRY_CODE
    regions["admin_level"] = 0.5
    regions["admin_level_name"] = "region"
    regions["country_code"] = COUNTRY_CODE
    regions["country_name"] = COUNTRY_NAME
    return regions[["code", "name", "parent_code", "admin_level", "admin_level_name", "country_code", "country_name", "geometry"]]


def keep_public_columns(gdf: gpd.GeoDataFrame, wanted: Optional[List[str]] = None) -> gpd.GeoDataFrame:
    base = [
        "code", "name", "parent_code", "admin_level", "admin_level_name", "country_code", "country_name",
        "region_code", "region_name", "province_code", "province_name", "district_code", "district_name",
        "llg_code", "llg_name", "ward_code", "ward_name", "source_code", "source_name_column", "source_code_column",
    ]
    cols = [c for c in (wanted or base) if c in gdf.columns]
    if "geometry" not in cols:
        cols.append("geometry")
    out = gdf[cols].copy()
    for c in out.columns:
        if c != "geometry":
            out[c] = out[c].fillna("").astype(str)
    return out


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = keep_public_columns(gdf)
    gdf.to_file(path, driver="GeoJSON")


def write_empty_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"type": "FeatureCollection", "features": []}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def generate_geojson_files(layers: Dict[int, gpd.GeoDataFrame], out_year: Path) -> Dict[str, str]:
    geo_root = out_year / "geojson"
    created: Dict[str, str] = {}

    # Folder skeleton always exists.
    for folder in ["country", "regions", "provinces", "districts", "llgs", "wards"]:
        (geo_root / folder).mkdir(parents=True, exist_ok=True)

    country = create_country_layer(layers)
    regions = create_region_layer(layers[1])

    p_country = geo_root / "country" / "png-country.geojson"
    write_geojson(country, p_country)
    created["country"] = str(p_country.relative_to(out_year)).replace("\\", "/")

    p_regions = geo_root / "regions" / "png-regions.geojson"
    write_geojson(regions, p_regions)
    created["regions"] = str(p_regions.relative_to(out_year)).replace("\\", "/")

    # All layers.
    layer_files = {
        1: geo_root / "provinces" / "png-provinces-country.geojson",
        2: geo_root / "districts" / "png-districts-country.geojson",
        3: geo_root / "llgs" / "png-llgs-country.geojson",
        4: geo_root / "wards" / "png-wards-country.geojson",
    }
    for level, path in layer_files.items():
        if level in layers:
            write_geojson(layers[level], path)
            created[f"adm{level}_all"] = str(path.relative_to(out_year)).replace("\\", "/")
        elif level == 4:
            write_empty_placeholder(path)
            created[f"adm{level}_all"] = str(path.relative_to(out_year)).replace("\\", "/")

    # Provinces by region.
    for region_code, sub in layers[1].groupby("region_code"):
        if not str(region_code).strip():
            continue
        path = geo_root / "provinces" / "by-region" / f"png-provinces-region-{slug(region_code)}.geojson"
        write_geojson(sub, path)
        created[f"provinces_region_{region_code}"] = str(path.relative_to(out_year)).replace("\\", "/")

    # Districts by province.
    if 2 in layers:
        for province_code, sub in layers[2].groupby("province_code"):
            if not str(province_code).strip():
                continue
            path = geo_root / "districts" / "by-province" / f"png-districts-province-{slug(province_code)}.geojson"
            write_geojson(sub, path)
            created[f"districts_province_{province_code}"] = str(path.relative_to(out_year)).replace("\\", "/")

    # LLGs by district.
    if 3 in layers:
        for district_code, sub in layers[3].groupby("district_code"):
            if not str(district_code).strip():
                continue
            path = geo_root / "llgs" / "by-district" / f"png-llgs-district-{slug(district_code)}.geojson"
            write_geojson(sub, path)
            created[f"llgs_district_{district_code}"] = str(path.relative_to(out_year)).replace("\\", "/")

    # Wards by LLG.
    if 4 in layers:
        for llg_code, sub in layers[4].groupby("llg_code"):
            if not str(llg_code).strip():
                continue
            path = geo_root / "wards" / "by-llg" / f"png-wards-llg-{slug(llg_code)}.geojson"
            write_geojson(sub, path)
            created[f"wards_llg_{llg_code}"] = str(path.relative_to(out_year)).replace("\\", "/")

    return created


def topo_output_path(out_year: Path, geo_path: Path, res: str) -> Path:
    # Mirror geojson structure under topojson, then insert resolution folder after level folder.
    rel = geo_path.relative_to(out_year / "geojson")
    parts = list(rel.parts)
    level_folder = parts[0]
    rest = parts[1:]
    filename = rest[-1].replace(".geojson", f".topo.json")
    rest[-1] = filename
    return out_year / "topojson" / level_folder / res / Path(*rest)


def convert_geojson_to_topojson(out_year: Path) -> List[str]:
    mapshaper = check_mapshaper()
    topo_files = []
    geo_files = list((out_year / "geojson").rglob("*.geojson"))
    if not geo_files:
        return topo_files
    for geo_file in geo_files:
        # Skip empty placeholder wards country file to avoid mapshaper issues.
        try:
            raw = json.loads(geo_file.read_text(encoding="utf-8"))
            if len(raw.get("features", [])) == 0:
                continue
        except Exception:
            pass
        for res, pct in RESOLUTIONS.items():
            out = topo_output_path(out_year, geo_file, res)
            out.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                mapshaper,
                str(geo_file),
                "-clean",
                "-simplify", pct, "keep-shapes",
                "-o", "format=topojson", str(out),
            ]
            run(cmd)
            topo_files.append(str(out.relative_to(out_year)).replace("\\", "/"))
    return topo_files


def feature_records(gdf: gpd.GeoDataFrame, fields: List[str]) -> List[dict]:
    records = []
    for _, row in gdf.sort_values([c for c in fields if c in gdf.columns]).iterrows():
        item = {}
        for f in fields:
            if f in gdf.columns:
                val = row.get(f, "")
                item[f] = "" if pd.isna(val) else str(val)
        records.append(item)
    return records


def build_index(layers: Dict[int, gpd.GeoDataFrame], out_year: Path, source_meta: List[SourceMeta], created: Dict[str, str], topo_files: List[str]) -> None:
    def topo(path: str, res: str = "medres") -> str:
        if not path:
            return ""
        p = Path(path)
        parts = list(p.parts)
        if parts[0] != "geojson":
            return ""
        level = parts[1]
        rest = parts[2:]
        filename = rest[-1].replace(".geojson", ".topo.json")
        rest[-1] = filename
        return str(Path("topojson") / level / res / Path(*rest)).replace("\\", "/")

    country_map = created.get("country", "")
    regions_map = created.get("regions", "")
    idx = {
        "country": {
            "code": COUNTRY_CODE,
            "name": COUNTRY_NAME,
            "geojson": country_map,
            "topojson_medres": topo(country_map),
        },
        "hierarchy": ["country", "region", "province", "district", "llg", "ward"],
        "maps": {
            "regions": {"geojson": regions_map, "topojson_medres": topo(regions_map)},
            "provinces_all": {"geojson": created.get("adm1_all", ""), "topojson_medres": topo(created.get("adm1_all", ""))},
            "districts_all": {"geojson": created.get("adm2_all", ""), "topojson_medres": topo(created.get("adm2_all", ""))},
            "llgs_all": {"geojson": created.get("adm3_all", ""), "topojson_medres": topo(created.get("adm3_all", ""))},
            "wards_all": {"geojson": created.get("adm4_all", ""), "topojson_medres": topo(created.get("adm4_all", ""))},
        },
        "regions": [],
        "provinces": [],
        "districts": [],
        "llgs": [],
        "wards": [],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_layers": [m.__dict__ for m in source_meta],
    }

    # Region records.
    regions = create_region_layer(layers[1])
    for _, row in regions.sort_values("code").iterrows():
        code = str(row["code"])
        gj = created.get(f"provinces_region_{code}", "")
        idx["regions"].append({
            "code": code,
            "name": str(row["name"]),
            "parent_code": COUNTRY_CODE,
            "provinces_geojson": gj,
            "provinces_topojson_medres": topo(gj),
        })

    # Provinces, districts, llgs, wards.
    for _, row in layers[1].sort_values("name").iterrows():
        code = str(row["code"])
        gj = created.get(f"districts_province_{code}", "")
        idx["provinces"].append({
            "code": code,
            "name": str(row["name"]),
            "parent_code": COUNTRY_CODE,
            "region_code": str(row.get("region_code", "")),
            "region_name": str(row.get("region_name", "")),
            "districts_geojson": gj,
            "districts_topojson_medres": topo(gj),
        })
    if 2 in layers:
        for _, row in layers[2].sort_values(["province_code", "name"]).iterrows():
            code = str(row["code"])
            gj = created.get(f"llgs_district_{code}", "")
            idx["districts"].append({
                "code": code,
                "name": str(row["name"]),
                "parent_code": str(row.get("province_code", row.get("parent_code", ""))),
                "province_code": str(row.get("province_code", "")),
                "province_name": str(row.get("province_name", "")),
                "llgs_geojson": gj,
                "llgs_topojson_medres": topo(gj),
            })
    if 3 in layers:
        for _, row in layers[3].sort_values(["district_code", "name"]).iterrows():
            code = str(row["code"])
            gj = created.get(f"wards_llg_{code}", "")
            idx["llgs"].append({
                "code": code,
                "name": str(row["name"]),
                "parent_code": str(row.get("district_code", row.get("parent_code", ""))),
                "district_code": str(row.get("district_code", "")),
                "district_name": str(row.get("district_name", "")),
                "province_code": str(row.get("province_code", "")),
                "province_name": str(row.get("province_name", "")),
                "wards_geojson": gj,
                "wards_topojson_medres": topo(gj),
            })
    if 4 in layers:
        for _, row in layers[4].sort_values(["llg_code", "name"]).iterrows():
            idx["wards"].append({
                "code": str(row["code"]),
                "name": str(row["name"]),
                "parent_code": str(row.get("llg_code", row.get("parent_code", ""))),
                "llg_code": str(row.get("llg_code", "")),
                "llg_name": str(row.get("llg_name", "")),
                "district_code": str(row.get("district_code", "")),
                "province_code": str(row.get("province_code", "")),
            })

    (out_year / "index.json").write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    meta = {
        "generated_at_utc": idx["generated_at_utc"],
        "generator": "png_json_maps_auto.py",
        "country": COUNTRY_NAME,
        "levels_detected": {f"adm{k}": len(v) for k, v in sorted(layers.items())},
        "geojson_files_created": len(created),
        "topojson_files_created": len(topo_files),
        "source_layers": [m.__dict__ for m in source_meta],
        "notes": [
            "Primary source is geoBoundaries gbOpen automated API unless local files are provided in a future version.",
            "PNG hierarchy is represented as country -> region -> province -> district -> LLG -> ward.",
            "Ward boundaries are generated only if an ADM4 geometry layer is available from the selected open source.",
            "Codes for ADM2+ may be generated when the open dataset does not provide official parent codes.",
        ],
    }
    (out_year / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatically generate PNG GeoJSON/TopoJSON hierarchy maps.")
    parser.add_argument("--year", default="2026", help="Output year folder, e.g. 2026")
    parser.add_argument("--out", default="./png-json-maps", help="Output root folder")
    parser.add_argument("--work", default="./_png-map-work", help="Working/source download folder")
    parser.add_argument("--include-wards", action="store_true", help="Try to download ADM4/ward geometry. If unavailable, skip safely.")
    parser.add_argument("--skip-topojson", action="store_true", help="Only generate GeoJSON/index, skip mapshaper TopoJSON conversion.")
    args = parser.parse_args()

    out_root = Path(args.out).resolve()
    work = Path(args.work).resolve()
    out_year = out_root / str(args.year)
    out_year.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    log(f"Output: {out_year}")
    log(f"Work: {work}")

    levels_to_try = [0, 1, 2, 3] + ([4] if args.include_wards else [])
    source_meta: List[SourceMeta] = []
    layer_paths: Dict[int, Path] = {}
    for level in levels_to_try:
        meta = download_geoboundaries(level, work)
        if meta:
            source_meta.append(meta)
            layer_paths[level] = Path(meta.downloaded_to)

    if 1 not in layer_paths:
        raise RuntimeError("Could not download ADM1/province boundaries. Check internet connection or geoBoundaries availability.")

    # Read and normalize.
    layers: Dict[int, gpd.GeoDataFrame] = {}
    for level, path in sorted(layer_paths.items()):
        gdf = read_layer(path)
        gdf = normalize_layer(gdf, level)
        layers[level] = gdf
        log(f"ADM{level}: {len(gdf)} features loaded")

    layers = enrich_context(layers)

    # Save GeoJSON hierarchy.
    created = generate_geojson_files(layers, out_year)
    log(f"GeoJSON files created: {len(created)}")

    topo_files: List[str] = []
    if args.skip_topojson:
        log("Skipping TopoJSON conversion.")
    else:
        topo_files = convert_geojson_to_topojson(out_year)
        log(f"TopoJSON files created: {len(topo_files)}")

    build_index(layers, out_year, source_meta, created, topo_files)
    log("DONE")
    print("\nGenerated map repo:")
    print(f"  {out_year}")
    print("\nImportant files:")
    print(f"  {out_year / 'index.json'}")
    print(f"  {out_year / 'metadata.json'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
