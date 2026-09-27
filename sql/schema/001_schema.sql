-- Phase 4: schema and type setup.
--
-- Two schemas: `staging` is a transient landing zone (truncated and reloaded on every
-- pipeline run); `warehouse` holds the durable star schema. Idempotent by design (safe
-- to run on every pipeline start, not just first container boot) so it works whether
-- Postgres init scripts have already run or the loader is applying it as a safety net.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_status_enum') THEN
        CREATE TYPE warehouse.transaction_status_enum AS ENUM (
            'valid_sale',
            'cancellation',
            'potential_return',
            'non_standard'
        );
    END IF;
END $$;
