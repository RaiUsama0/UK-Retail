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
running `ingest-data` (see the README) against the actual dataset — never hand-typed.
The full, up-to-date profiling output is regenerated at `reports/data_profile.md` /
`reports/data_profile.json` on every run.

## Raw columns (as published)

| Column | Raw dtype (pandas) | Description | Verified data quality notes |
|---|---|---|---|
| `InvoiceNo` | object | Invoice number. A 6-digit integer, uniquely assigned per transaction; **prefixed `C` if the transaction is a cancellation**. | 25,900 unique values; 9,288 rows start with `C`. |
| `StockCode` | object | Product/item code. A 5-digit integer, uniquely assigned per product; some non-product codes exist (e.g. `POST`, `D`, `M`, `BANK CHARGES`). | 4,070 unique values. |
| `Description` | object | Product name. | 1,454 rows (0.3%) missing — these rows are also `UnitPrice = 0` and missing `CustomerID`, consistent with manual adjustment entries rather than real sales. |
| `Quantity` | int64 | Quantity of each product per transaction. | Range -80,995 to 80,995. 10,624 rows negative. Of these, 9,288 correspond to a cancelled invoice (`InvoiceNo` starting with `C`); the remaining 1,336 are negative-quantity rows **not** flagged as a cancellation ("potential returns" — flagged for review, not assumed invalid). |
| `InvoiceDate` | datetime64 | Date and time the transaction was generated. | Range 2010-12-01 08:26 to 2011-12-09 12:50. No missing values. |
| `UnitPrice` | float64 | Unit price in pounds sterling (GBP). | Range -£11,062.06 to £38,970. 2,517 rows are ≤ 0 (2 negative, 2,515 exactly zero) — these are not genuine product sales (adjustments/write-offs), and are excluded from revenue KPIs (documented in `kpi_definitions.md`). |
| `CustomerID` | float64 (loaded; NA-forcing) | A 5-digit integer, uniquely assigned per customer. | **135,080 rows (24.9%) missing.** Not all missing values represent invalid transactions — many are legitimate sales without a registered customer account. Product-level KPIs include these rows; customer-level KPIs (repeat rate, RFM) exclude them, with the exclusion documented and its effect quantified in the cleaning report. |
| `Country` | object | Name of the country where the customer resides. | 38 distinct values. 91% of rows are `United Kingdom`. No reliable UK sub-national/regional geography is present in the source data — regional breakdowns are out of scope unless a future enrichment step adds one. |

## Derived / pipeline columns (added during cleaning — Phase 3)

| Column | Type | Description |
|---|---|---|
| `transaction_type` | categorical | One of `sale`, `cancellation`, `return`, `questionable` — classification logic documented in `docs/kpi_definitions.md` and the cleaning report. |
| `line_id` | surrogate key | Deterministic technical identifier for each invoice line, since the raw data has no native line-level primary key (see `docs/architecture/` for the exact derivation). |

## Known dataset limitations

- No product cost or margin data — profit cannot be calculated, only revenue.
- No shipping cost data.
- No customer demographic data beyond country.
- No reliable UK regional/postcode geography.
- A single export snapshot, not a live/streaming source.
