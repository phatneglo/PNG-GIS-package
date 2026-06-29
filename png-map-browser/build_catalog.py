#!/usr/bin/env python3
"""Build png-map-browser/catalog.json from generated png-json-maps year folders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAPS_DIR = ROOT / "png-json-maps"
BROWSER_DIR = ROOT / "png-map-browser"
EMBEDDED_MAPS_DIR = BROWSER_DIR / "png-json-maps"
CATALOG_FILE = BROWSER_DIR / "catalog.json"


def main() -> None:
    years = []
    maps_dir = EMBEDDED_MAPS_DIR if EMBEDDED_MAPS_DIR.exists() else MAPS_DIR
    data_root = "png-json-maps" if maps_dir == EMBEDDED_MAPS_DIR else "../png-json-maps"

    if maps_dir.exists():
        for child in maps_dir.iterdir():
            if child.is_dir() and child.name.isdigit() and (child / "index.json").exists():
                years.append(
                    {
                        "year": child.name,
                        "index": f"{data_root}/{child.name}/index.json",
                        "metadata": f"{data_root}/{child.name}/metadata.json",
                    }
                )

    years.sort(key=lambda item: int(item["year"]), reverse=True)
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "years": years,
    }

    BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {CATALOG_FILE} with {len(years)} year(s).")


if __name__ == "__main__":
    main()
