-- Dimension tables. Each has a surrogate technical key (SERIAL) kept separate from its
-- real-world business key, per the project's identifier-separation convention.
--
-- dim_customer deliberately has NO country column: inspection of the cleaned dataset
-- showed 8 of 4,372 customers (0.18%) transacted from more than one country, so
-- country is not a stable customer attribute here. Country is modelled only as its own
-- dimension, joined directly from fact_sales (see docs/data_dictionary.md).
--
-- dim_product.description is the mode (most frequent non-null value) of that
-- stock_code's observed descriptions, not assumed unique: 647 of 4,070 stock codes
-- have more than one distinct non-null description in the source data (often a
-- genuine description alongside an inventory annotation like "damaged" or "check").
-- description_variant_count records how many distinct descriptions were observed.

CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key     INTEGER PRIMARY KEY,          -- YYYYMMDD
    date_value   DATE NOT NULL UNIQUE,
    year         SMALLINT NOT NULL,
    quarter      SMALLINT NOT NULL,
    month        SMALLINT NOT NULL,
    month_name   TEXT NOT NULL,
    day          SMALLINT NOT NULL,
    day_of_week  SMALLINT NOT NULL,             -- 0=Monday .. 6=Sunday (ISO-ish, Python convention)
    day_name     TEXT NOT NULL,
    is_weekend   BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse.dim_country (
    country_key   SERIAL PRIMARY KEY,
    country_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS warehouse.dim_customer (
    customer_key  SERIAL PRIMARY KEY,
    customer_id   INTEGER NOT NULL UNIQUE       -- original business identifier from the source
);

CREATE TABLE IF NOT EXISTS warehouse.dim_product (
    product_key                SERIAL PRIMARY KEY,
    stock_code                 TEXT NOT NULL UNIQUE,   -- original business identifier from the source
    description                TEXT,
    description_variant_count  INTEGER NOT NULL DEFAULT 0
);
