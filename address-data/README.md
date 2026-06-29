# PNG Address Data

Generated public address data exports for Papua New Guinea.

Each year folder contains the same address records in multiple formats:

- `address-records.json` - canonical flat records with metadata and schema.
- `address-hierarchy.json` - nested country, region, province, district, LLG, and ward hierarchy.
- `address-records.csv` - UTF-8 CSV for spreadsheets and bulk imports.
- `address-records.xml` - XML for systems that prefer document exchange.
- `png-address-data.sql` - PostgreSQL-compatible table, inserts, metadata, and indexes.
- `schema.json` - field definitions and data types.
- `metadata.json` - counts, source notes, and generation metadata.

Use `record_id` as the unique row key. The `code` field is still useful for lookups, but some supplemental ward source records can share generated codes.
