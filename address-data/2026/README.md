# PNG Address Data 2026

This folder contains the generated Papua New Guinea address package in common import formats.

## Files

- `address-records.json` - canonical flat records with metadata and schema.
- `address-hierarchy.json` - nested country -> region -> province -> district -> LLG -> ward hierarchy.
- `address-records.csv` - spreadsheet/import friendly flat records, UTF-8 with BOM.
- `address-records.xml` - XML flat records with stable element names.
- `png-address-data.sql` - PostgreSQL-compatible SQL table, metadata, inserts, and indexes.
- `schema.json` - column definitions and data types.
- `metadata.json` - generation metadata, counts, source notes, and hierarchy notes.

## Counts

- `district`: 87
- `llg`: 326
- `province`: 22
- `region`: 4
- `ward`: 6,418

## Notes

- Province codes use ISO 3166-2:PG where available.
- District, LLG, and some ward codes are package-generated where no official code is available.
- Ward records may be address/search records only; check `geometry_available` before treating a ward as a mapped polygon.
