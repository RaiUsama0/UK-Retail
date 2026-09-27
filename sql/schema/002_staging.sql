-- Transient landing table: one row per Phase 3 cleaned-dataset row, columns matching
-- data/processed/online_retail_cleaned.parquet almost verbatim. No constraints here on
-- purpose — this is a raw landing zone, truncated and bulk-loaded (COPY) on every
-- pipeline run; all real constraints live on the warehouse tables it feeds.

CREATE TABLE IF NOT EXISTS staging.stg_cleaned_sales (
    source_row_id                     INTEGER NOT NULL,
    invoice_no                        TEXT NOT NULL,
    stock_code                        TEXT NOT NULL,
    description                       TEXT,
    quantity                          INTEGER NOT NULL,
    invoice_date                      TIMESTAMP NOT NULL,
    unit_price                        NUMERIC(12, 4) NOT NULL,
    customer_id                       INTEGER,
    country                           TEXT NOT NULL,
    transaction_status                TEXT NOT NULL,
    line_revenue                      NUMERIC(14, 2) NOT NULL,
    flag_missing_customer_id          BOOLEAN NOT NULL,
    flag_missing_description          BOOLEAN NOT NULL,
    flag_non_positive_price           BOOLEAN NOT NULL,
    flag_zero_quantity                BOOLEAN NOT NULL,
    flag_duplicate_candidate          BOOLEAN NOT NULL,
    flag_non_standard_invoice_format  BOOLEAN NOT NULL,
    flag_non_standard_stock_code      BOOLEAN NOT NULL
);
