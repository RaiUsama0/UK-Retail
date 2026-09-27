-- fact_sales grain: one row per Phase 3 cleaned-dataset row (= one row per original
-- raw invoice line). Primary key is source_row_id, reused directly from Phase 3 — a
-- deterministic technical identifier, NOT a second, redundant surrogate key. The
-- business identifier (invoice_no) is kept as its own column, separate from the
-- technical primary key.
--
-- customer_key is nullable by design: CustomerID is missing for 24.93% of source
-- rows, and no customer identity is invented for them.
--
-- All 541,909 cleaned rows are loaded here, including duplicate-candidate rows,
-- cancellations, potential returns, and non-standard transactions — nothing is
-- filtered out of the fact table itself. Analytical views (006_views.sql) provide
-- filtered/aggregated perspectives on top of this complete table.

CREATE TABLE IF NOT EXISTS warehouse.fact_sales (
    source_row_id                     INTEGER PRIMARY KEY,
    invoice_no                        TEXT NOT NULL,
    product_key                       INTEGER NOT NULL REFERENCES warehouse.dim_product (product_key),
    customer_key                      INTEGER REFERENCES warehouse.dim_customer (customer_key),
    country_key                       INTEGER NOT NULL REFERENCES warehouse.dim_country (country_key),
    date_key                          INTEGER NOT NULL REFERENCES warehouse.dim_date (date_key),
    invoice_timestamp                 TIMESTAMP NOT NULL,
    quantity                          INTEGER NOT NULL,
    unit_price                        NUMERIC(12, 4) NOT NULL,
    line_revenue                      NUMERIC(14, 2) NOT NULL,
    transaction_status                warehouse.transaction_status_enum NOT NULL,
    flag_missing_customer_id          BOOLEAN NOT NULL,
    flag_missing_description          BOOLEAN NOT NULL,
    flag_non_positive_price           BOOLEAN NOT NULL,
    flag_zero_quantity                BOOLEAN NOT NULL,
    flag_duplicate_candidate          BOOLEAN NOT NULL,
    flag_non_standard_invoice_format  BOOLEAN NOT NULL,
    flag_non_standard_stock_code      BOOLEAN NOT NULL,

    CONSTRAINT chk_source_row_id_non_negative CHECK (source_row_id >= 0)
);
