# Data Dictionary — Online Retail Dataset

**Source:** UCI Machine Learning Repository, "Online Retail" dataset
(<https://archive.ics.uci.edu/dataset/352/online+retail>).

**Nature of the data:** a historical, static export of transactions from a UK-based
online gift retailer, covering **2010-12-01 to 2011-12-09**. It is not a live feed —
all documentation and dashboards must describe it as historical.

**Licence / usage:** UCI ML Repository datasets are made available for research and
educational use; this project uses it strictly for a non-commercial portfolio
demonstration and credits the source as above.

**Provenance and reproducibility:** all data quality figures below are computed by
running `ingest-data` / `ingest-data clean` (see the README) against the actual
dataset — never hand-typed. The full, up-to-date output is regenerated at
`reports/data_profile.{json,md}` and `reports/cleaning_summary.{json,md}` on every run.

## Raw columns (as published)

| Column | Raw dtype (pandas) | Description | Verified data quality notes |
|---|---|---|---|
| `InvoiceNo` | object | Invoice number. A 6-digit integer, uniquely assigned per transaction; **prefixed `C` if the transaction is a cancellation**. | 25,900 unique values; 9,288 rows start with `C`. **3 rows** don't match the normal `^C?\d{6}$` pattern at all (`InvoiceNo` like `A563185`) — a set of "Adjust bad debt" manual accounting entries, `StockCode = 'B'`, one with a *positive* price (£11,062.06) and positive quantity that would otherwise look like an ordinary sale. |
| `StockCode` | object | Product/item code. A 5-digit integer, uniquely assigned per product; some non-product codes exist (e.g. `POST`, `D`, `M`, `BANK CHARGES`). | 4,070 unique values. **2,995 rows (0.55%)** have a code that doesn't start with a digit (`POST` 1,256, `DOT` 710, `M` 571, `C2` 144, `D` 77, `S` 63, `BANK CHARGES` 37, `AMAZONFEE` 34, `CRUK` 16, `DCGS*` gift-set codes, `gift_0001_*`, `PADS`, `B`) — flagged informationally, not treated as invalid, since several (e.g. `POST`) are genuine, correctly-priced charges. |
| `Description` | object | Product name. | 1,454 rows (0.3%) missing. 113,452 rows have leading/trailing whitespace (normalised during cleaning). No rows are blank-after-strip. |
| `Quantity` | int64 | Quantity of each product per transaction. | Range -80,995 to 80,995. 10,624 rows negative. Of these, 9,288 correspond to a cancelled invoice (`InvoiceNo` starting with `C`); the remaining 1,336 are negative-quantity rows **not** flagged as a cancellation ("potential returns"). 0 rows have `Quantity == 0`. |
| `InvoiceDate` | datetime64 | Date and time the transaction was generated. | Range 2010-12-01 08:26 to 2011-12-09 12:50. No missing/invalid values. |
| `UnitPrice` | float64 | Unit price in pounds sterling (GBP). | Range -£11,062.06 to £38,970. 2,517 rows are ≤ 0 (2 negative, 2,515 exactly zero). **All 1,336 potential-return rows have `UnitPrice == 0` exactly** — verified, not assumed. |
| `CustomerID` | float64 (loaded; NA-forcing) | A 5-digit integer, uniquely assigned per customer. | **135,080 rows (24.93%) missing.** Not all missing values represent invalid transactions — many are legitimate sales without a registered customer account. **All 1,336 potential-return rows are also missing `CustomerID`.** Product-level KPIs include these rows; customer-level KPIs (repeat rate, RFM) exclude them. |
| `Country` | object | Name of the country where the customer resides. | 38 distinct values. 91% of rows are `United Kingdom`. No reliable UK sub-national/regional geography is present in the source data. |

## Cleaned dataset schema (`data/processed/online_retail_cleaned.parquet`, Phase 3)

Every raw row maps to exactly one cleaned row (row count is never changed by
cleaning); columns are renamed to snake_case. Real, verified counts against the full
dataset are in `reports/cleaning_summary.md`.

| Column | Type | Description |
|---|---|---|
| `source_row_id` | int64 | **Technical** identifier = the row's 0-based position in the raw file at load time. **Not a business transaction ID** — the raw data has none at the line-item grain. Stable only as long as the raw file's row order is unchanged (guaranteed by the ingestion checksum). |
| `invoice_no`, `stock_code`, `description`, `country` | string | Raw values, whitespace-stripped. `description` uses pandas' nullable `string` dtype so a blank/whitespace-only value becomes a proper missing value, not an empty string. |
| `quantity`, `unit_price` | int64, float64 | Unchanged from raw. |
| `invoice_date` | datetime64 | Re-parsed with `errors="coerce"` so a genuinely invalid date becomes a detectable `NaT` (0 found in the real dataset). |
| `customer_id` | nullable Int64 | Raw `CustomerID`, cast from float64 to a proper nullable integer type. |
| `transaction_status` | category | One of `valid_sale`, `cancellation`, `potential_return`, `non_standard` — see `docs/kpi_definitions.md` for the exact precedence rule. |
| `line_revenue` | float64 | `quantity * unit_price`, computed via `Decimal` and quantized to whole pence (`ROUND_HALF_UP`) — avoids float64 rounding artefacts on individual lines; report-level totals are summed in `Decimal` directly to avoid accumulation drift over 540k+ rows. |
| `flag_missing_customer_id` | bool | `customer_id` is null. |
| `flag_missing_description` | bool | `description` is null. |
| `flag_non_positive_price` | bool | `unit_price <= 0`. |
| `flag_zero_quantity` | bool | `quantity == 0`. |
| `flag_duplicate_candidate` | bool | Row is an exact duplicate of another row (all original columns identical, excluding `source_row_id`). Preserved, never auto-dropped — see the duplicate policy in `docs/kpi_definitions.md`. |
| `flag_non_standard_invoice_format` | bool | `invoice_no` doesn't match `^C?\d{6}$`. |
| `flag_non_standard_stock_code` | bool | `stock_code` doesn't start with a digit — informational only, does not affect `transaction_status`. |

## PostgreSQL warehouse schema (Phase 4)

Full ER diagram and design rationale: `docs/architecture/overview.md`. Loaded via
`ingest-data load-warehouse`; verified against the real 541,909-row dataset.

| Table | Grain | Key(s) |
|---|---|---|
| `warehouse.fact_sales` | One row per cleaned-dataset row (= one row per raw invoice line) | PK `source_row_id` (reused directly from Phase 3 — no second surrogate key) |
| `warehouse.dim_product` | One row per distinct `stock_code` (4,070 rows) | PK `product_key`; business key `stock_code` (UNIQUE) |
| `warehouse.dim_customer` | One row per distinct known `customer_id` (4,372 rows — no synthetic "unknown customer" row) | PK `customer_key`; business key `customer_id` (UNIQUE) |
| `warehouse.dim_country` | One row per distinct country (38 rows) | PK `country_key`; business key `country_name` (UNIQUE) |
| `warehouse.dim_date` | One row per calendar day spanning the observed date range (374 rows) | PK `date_key` (INTEGER, `YYYYMMDD`) |
| `staging.stg_cleaned_sales` | Transient landing table, truncated and bulk-loaded (`COPY`) every run | No constraints — not the source of truth |

Verified, not assumed, going into this design:
- **647 of 4,070 stock codes have more than one distinct non-null description**
  (often a genuine description plus an inventory annotation like `"damaged"` or
  `"check"`) — `dim_product.description` is the `MODE()` of observed descriptions,
  with `description_variant_count` recording how many were seen.
- **8 of 4,372 customers transacted from more than one country** — so `dim_customer`
  deliberately has no country column; country is modelled only via `dim_country`,
  joined directly from `fact_sales`.
- `fact_sales.customer_key` is **nullable** — no customer identity is invented for the
  24.93% of rows with a missing `CustomerID`.

Idempotency: `INSERT ... ON CONFLICT DO UPDATE/DO NOTHING` upserts keyed on real
primary/unique keys, inside a single transaction per load. Verified by loading the
real dataset twice and confirming `fact_sales` still has exactly 541,909 rows both
times, with all reconciliation checks passing — see `reports/warehouse_load_report.md`.

## Known dataset limitations

- No product cost or margin data — profit cannot be calculated, only revenue.
- No shipping cost data.
- No customer demographic data beyond country.
- No reliable UK regional/postcode geography.
- A single export snapshot, not a live/streaming source.
- **Passing structural and cleaning validation is not the same as the data being fully
  accurate.** Validation confirms internal consistency (row counts preserved, every
  row classified, `line_revenue` arithmetic correct) — it cannot confirm that, say, a
  `valid_sale` row's `Quantity`/`UnitPrice` were recorded correctly at the source. The
  `non_standard`, `potential_return`, and duplicate-candidate flags exist precisely
  because a meaningful share of rows (about 2.4% combined) don't inspire that
  confidence, and are reported separately rather than folded into "clean" data.
