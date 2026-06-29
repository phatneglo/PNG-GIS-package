# PNG JSON Maps

Open Papua New Guinea administrative boundary maps and address hierarchy JSON for frontend apps, map browsing, and address autocomplete.

Created by **Roniel Nuqui** / **[@phatneglo](https://github.com/phatneglo)**.

This project generates a PNG map package similar in spirit to `philippines-json-maps`, but adapted to Papua New Guinea's administrative structure:

```text
country -> region -> province -> district -> LLG -> ward
```

The current open `gbOpen` source output used by this package contains usable boundaries down to **LLG**. Ward folders are kept for compatibility, but the 2026 generated ward GeoJSON is an empty placeholder because ADM4/ward geometry is not available from the selected open source.

## What This Includes

- `png-json-maps/<year>/`
  GeoJSON and TopoJSON boundary files for PNG country, regions, provinces, districts, and LLGs.
- `png-json-address/<year>/`
  Address hierarchy JSON and flat autocomplete records generated from the map index, with supplemental text-only ward names.
- `address-data/<year>/`
  Public address exports in JSON, CSV, XML, and SQL for different application/database needs.
- `png-map-browser/`
  Standalone Leaflet + Bootstrap browser for viewing map layers and searching PNG addresses.
- `scripts/`
  Python generators for maps and address JSON.

## Quick Start

Run from Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_and_generate_png_maps.ps1 -Year 2026
```

This will:

- check/install required tooling where possible
- create a local Python virtual environment
- download PNG open boundary data
- generate GeoJSON and TopoJSON files
- generate address hierarchy and autocomplete JSON
- export address data to JSON, CSV, XML, and SQL
- refresh the map browser catalog

To also try ADM4 / ward geometry:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_and_generate_png_maps.ps1 -Year 2026 -IncludeWards
```

If ward geometry is not available, the generator skips it safely.

## Output Structure

```text
png-json-maps/
  2026/
    geojson/
      country/
      regions/
      provinces/
      districts/
      llgs/
      wards/
    topojson/
      country/
      regions/
      provinces/
      districts/
      llgs/
      wards/
    index.json
    metadata.json

png-json-address/
  2026/
    address-hierarchy.json
    address-flat.json

address-data/
  README.md
  2026/
    metadata.json
    schema.json
    address-records.json
    address-hierarchy.json
    address-records.csv
    address-records.xml
    png-address-data.sql

png-map-browser/
  index.html
  assets/
  vendor/
  catalog.json
```

## Address JSON

Use `address-flat.json` for autocomplete:

```json
{
  "code": "PG-CPK-D001-L001",
  "name": "Chuave Rural LLG",
  "level": "llg",
  "label": "Chuave Rural LLG, Chuave District, Chimbu (Simbu) Province, Highlands Region, Papua New Guinea",
  "code_system": "png-json-maps-generated",
  "standard_code": "",
  "is_standard_code": false,
  "region_code": "HIGHLANDS",
  "province_code": "PG-CPK",
  "district_code": "PG-CPK-D001",
  "llg_code": "PG-CPK-D001-L001"
}
```

### Code Standards

This is not a PNG version of PSGC. The generated JSON is explicit about code provenance:

- Country code `PNG` uses ISO 3166-1 alpha-3.
- Province codes such as `PG-CPM`, `PG-NCD`, and `PG-NSB` use ISO 3166-2:PG-style subdivision codes from the source `shapeISO`.
- Region codes such as `HIGHLANDS` and `MOMASE` are package grouping codes.
- District and LLG codes such as `PG-CPM-D001` and `PG-CPM-D001-L001` are generated stable package codes because the current source data has blank `shapeISO` values for ADM2 and ADM3.
- Ward address codes such as `PG-SAN-D004-L003-W001` are generated from supplemental text data and parent LLG matches. They do not imply ward boundary geometry.

Every address record includes:

```text
code_system
standard_code
is_standard_code
source_code
source_code_column
code_note
```

Use `is_standard_code` before treating a code as an official external registry code.

Use `address-hierarchy.json` for cascading selects:

```text
country
  regions[]
    provinces[]
      districts[]
        llgs[]
          wards[]
```

For the current 2026 output:

```text
regions: 4
provinces: 22
districts: 87
llgs: 326
wards: 0
ward address records: 6418
ward boundary records: 0
autocomplete records: 6857
```

`address-hierarchy.json` also includes an `administrative_hierarchy` section so apps can understand unavailable deeper levels:

```text
country -> region -> province -> district -> LLG -> ward -> census unit
```

For 2026, `ward.available_in_address_json` is `true` because supplemental text-only ward names are included from `papua-new-guinea-geolist`. `ward.available_as_boundary` is still `false` because the current generated boundary source has no ADM4/ward geometry.

Each ward address record includes:

```text
level: ward
matched_to_map
has_boundary: false
geometry_available: false
source_dataset
```

When a ward is matched to one of our LLG boundary records, it receives a generated address code like `PG-SAN-D004-L003-W001`. This code is for app use only and is not a verified government registry code.

## Address Data Exports

Use `address-data/<year>/` when you need import-ready files outside the map browser:

```text
address-records.json   canonical flat records with metadata and schema
address-hierarchy.json nested hierarchy
address-records.csv    UTF-8 CSV for spreadsheets and ETL
address-records.xml    XML document exchange format
png-address-data.sql   PostgreSQL-compatible table, inserts, metadata, indexes
schema.json            field definitions
metadata.json          counts and source notes
```

Use `record_id` as the unique row key. The `code` field remains useful for lookups, but some supplemental ward source records can share generated codes.

## Standalone Map Browser

Start a local web server from the package root:

```powershell
python -m http.server 8080
```

Open:

```text
http://localhost:8080/png-map-browser/
```

The browser includes:

- Leaflet map display
- Bootstrap UI
- local vendored CSS/JS assets under `png-map-browser/vendor`
- year selector
- map layer selector
- region/province/district/LLG drill-down
- address finder backed by `png-json-address/<year>/address-flat.json`
- optional OpenStreetMap and CARTO Light basemaps

If you deploy `png-map-browser` as a standalone folder, include these folders beside it or inside it:

```text
png-map-browser/
  index.html
  assets/
  vendor/
  catalog.json
  png-json-maps/
  png-json-address/
```

Then run:

```powershell
python .\png-map-browser\build_catalog.py
```

## Frontend Loading Pattern

For map drill-down, load `png-json-maps/<year>/index.json`:

```text
regions
-> click region
-> load provinces for that region
-> click province
-> load districts for that province
-> click district
-> load LLGs for that district
```

For address autocomplete, load:

```text
png-json-address/<year>/address-flat.json
```

For cascading address selectors, load:

```text
png-json-address/<year>/address-hierarchy.json
```

## Important PNG Mapping Note

PNG does not use Philippine-style City/Municipality in the same way. A practical mapping for app design is:

```text
Philippines Province       ~= PNG Province
Philippines City/Municipal ~= PNG LLG
Philippines Barangay       ~= PNG Ward, when available
Subdivision/Street         ~= Census Unit / Village / Locality / Street / Household point
```

The closest PNG equivalent to a Philippine barangay is generally a **Ward** under an LLG. Below ward, PNG census workflows may use **Census Units**, but those are not included in the current open boundary dataset.

## Source And Attribution

The default automatic source is geoBoundaries `gbOpen`, which provides programmatic API access and GeoJSON download URLs.

When using generated data publicly, include attribution for the source boundary datasets listed in each year's `metadata.json`.

Useful references:

- Humanitarian Data Exchange lists the PNG common operational boundary dataset as administrative levels 0-3, which corresponds to country through LLG in this package: https://data.humdata.org/dataset/cod-ab-png
- PNG National Statistical Office publishes census figures by wards by region, confirming wards exist as a statistical/admin level even when ward geometries are not present in the current boundary source: https://www.nso.gov.pg/wpfd_file/census-figures-by-wards-islands-region/
- geoBoundaries / HDX PNG ADM3 resources provide the LLG-level geometries used by the current generator output: https://data.humdata.org/organization/geoboundaries
- Supplemental ward names are loaded from Wilfred Wulbou's MIT-licensed PNG GeoList project: https://github.com/wilfred-wulbou/papua-new-guinea-geolist

## License

Add a repository license before publishing if this will be shared for public reuse. Recommended options are MIT for code and clear attribution notes for generated boundary data.
