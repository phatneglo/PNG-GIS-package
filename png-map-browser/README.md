# PNG Map Browser

Standalone Leaflet + Bootstrap browser for the generated `png-json-maps` and `png-json-address` folders.

## Run

From the package root:

```powershell
python .\png-map-browser\build_catalog.py
python -m http.server 8080
```

Open:

```text
http://localhost:8080/png-map-browser/
```

You can also deploy or copy the browser as a standalone folder if it contains:

```text
png-map-browser/
  index.html
  assets/
  vendor/
  catalog.json
  png-json-maps/
    <year>/
      index.json
  png-json-address/
    <year>/
      address-flat.json
```

For this standalone layout, run `build_catalog.py` after copying the maps so
`catalog.json` points to `png-json-maps/<year>/index.json`.

## Add Another Year

Generate maps into the usual structure:

```text
png-json-maps/<year>/index.json
```

Then refresh the browser catalog:

```powershell
python .\scripts\build_png_address_index.py --year 2026
python .\png-map-browser\build_catalog.py
```

The new year will appear in the year selector.

## Address Finder

The browser loads:

```text
png-json-address/<year>/address-flat.json
```

Use the Address finder input to search regions, provinces, districts, and LLGs.
Selecting a result switches to the correct map layer and zooms to that boundary.

## Notes

- Uses Leaflet with a reliable no-basemap default and optional OpenStreetMap / CARTO light tiles.
- Includes local Leaflet, Bootstrap, and Bootstrap Icons assets under `vendor/`, so the browser UI does not depend on CDN CSS or JS.
- Reads each year's `index.json` so drill-down paths stay aligned with the generated map package.
- Reads each year's `address-flat.json` for address autocomplete/search.
- The current generated PNG data has country, regions, provinces, districts, and LLGs. Ward boundaries are not shown unless a future generated year includes non-empty ward GeoJSON.
- Must be opened through a local web server because browser `fetch()` cannot reliably load local JSON files from `file://`.
