-- Indexes on fact_sales for the query patterns Phase 5's SQL analysis and Phase 6's
-- dashboards are expected to use: filtering/joining by date, customer, product,
-- invoice, and transaction status. Deliberately not indexing every column — see
-- docs/architecture/overview.md for EXPLAIN ANALYZE measurements once available.

CREATE INDEX IF NOT EXISTS idx_fact_sales_date_key ON warehouse.fact_sales (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer_key ON warehouse.fact_sales (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_product_key ON warehouse.fact_sales (product_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_invoice_no ON warehouse.fact_sales (invoice_no);
CREATE INDEX IF NOT EXISTS idx_fact_sales_transaction_status ON warehouse.fact_sales (transaction_status);
