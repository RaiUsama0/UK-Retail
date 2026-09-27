-- Section 6: COHORT RETENTION
--
-- Observation-window limitation: the dataset ends 2011-12-09. A cohort formed close to
-- that date has had little or no chance to show retention in later months, simply
-- because those months don't exist in the data. dataset_last_month (below) makes that
-- boundary explicit — a customer who "didn't return" in a month the dataset doesn't
-- cover is NOT confirmed churn, it's an unobserved period.

-- 6.1. Full cohort x activity-month retention matrix (as computed by the view).
SELECT cohort_month, activity_month, month_index, cohort_size, returning_customers,
       retention_pct, dataset_last_month
FROM warehouse.v_customer_cohort_retention
ORDER BY cohort_month, activity_month;

-- 6.2. Retention curve by month_index, averaged ONLY across cohorts that have actually
-- had the chance to be observed that far out (cohort_month + month_index <= dataset's
-- last complete-enough month) — avoids diluting, say, "month 6 retention" with cohorts
-- that only formed a month ago and have no month-6 data point at all (they simply
-- don't appear in the underlying view for that month_index, but mixing cohorts with
-- very different amounts of observed history still needs care — this query makes the
-- eligible-cohort-count explicit rather than hiding it).
SELECT
    month_index,
    COUNT(DISTINCT cohort_month) AS cohorts_observed_at_this_index,
    ROUND(AVG(retention_pct), 2) AS avg_retention_pct
FROM warehouse.v_customer_cohort_retention
WHERE month_index > 0
GROUP BY month_index
ORDER BY month_index;

-- 6.3. Cohort sizes (new identified customers acquired per month) — the November and
-- December 2011 cohorts are visibly smaller/truncated purely because the dataset ends
-- shortly after they were acquired, not necessarily because acquisition itself slowed.
SELECT DISTINCT cohort_month, cohort_size
FROM warehouse.v_customer_cohort_retention
ORDER BY cohort_month;
