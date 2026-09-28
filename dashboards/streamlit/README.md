# Streamlit Dashboard — Public Demo

**Status: implemented and verified locally. Not deployed.** Deployment requires
pushing this repository to GitHub and connecting a Streamlit Community Cloud account
— both require your authorisation and credentials, which I don't have. See "Public
deployment" below for the exact steps.

## What this is

A public, no-installation-required demo of the project's verified analytical
findings — 4 pages (Executive Overview, Product Performance, Customer Intelligence,
Transaction Quality), reading only from a privacy-reviewed set of aggregated CSV
extracts (`data/public/`, see that folder's own README for the full privacy review).
**No PostgreSQL connection is used or required at runtime** — this app can run
entirely offline once the CSVs exist.

These 15 CSVs **are committed to this repository** (unlike the internal Power BI
export) specifically so Streamlit Community Cloud — which has no database access —
can serve them. Regenerate with `ingest-data export-public` and commit the update
whenever the underlying pipeline changes; see `data/public/README.md` for the
per-file privacy rationale and the automated check that enforces it.

## Architecture

```
dashboards/streamlit/
  app.py                    - entry point / landing page
  pages/                    - the 4 dashboard pages (Streamlit's file-based multipage routing)
  streamlit_lib/
    config.py                - paths, constants, colour mapping (no secrets — nothing here needs protecting)
    data_loader.py            - cached CSV loading + lightweight schema validation
    metrics.py                - pure KPI/filter calculation functions (no Streamlit import — unit-testable directly)
    charts.py                 - Plotly figure builders (pure functions)
    ui.py                     - shared KPI cards, warning banners, footer
  data/public/               - the actual CSV data (committed — see below for why)
  requirements.txt            - deployment dependencies (streamlit + pandas + plotly only)
```

Data loading, metric calculation, filtering, charting, and UI rendering are
deliberately separated (see the file list above) — `metrics.py` and `charts.py` have
no Streamlit import at all, so they're tested directly with plain pytest, no
Streamlit runtime needed (`tests/test_streamlit_metrics.py`).

## Running locally

```bash
# 1. Install dependencies (from the repo root)
pip install -e ".[dashboard]"

# 2. Generate the public dataset (requires a local PostgreSQL connection — see the
#    main README's "Installation and setup"; this is the ONE step that needs the
#    database, and only to *refresh* the data, never at app runtime)
ingest-data export-public

# 3. Run the app
streamlit run dashboards/streamlit/app.py
```

Verified working: `streamlit run` was started, served `HTTP 200` and a healthy
`/_stcore/health` response, then was stopped — this is a real, executed check, not an
assumption. **Note**: Streamlit's default binds to all network interfaces
(`0.0.0.0`), which prints an "External URL" if the machine has one reachable — for
local development only, prefer:

```bash
streamlit run dashboards/streamlit/app.py --server.address localhost
```

## A real caching behaviour worth knowing (found while testing, not assumed)

`st.cache_data` caches by function arguments, not by the underlying file's content or
modification time. If you run `ingest-data export-public` again to refresh the data
**while the Streamlit process is still running**, the app will keep serving the old
cached values until either the process restarts or someone clears the cache from
Streamlit's UI (the "⋮" menu -> "Clear cache"). This was confirmed directly while
building the test suite (`tests/test_streamlit_app.py`'s cache-isolation fixture) — it
is not a hypothetical concern.

## Public deployment (Streamlit Community Cloud)

**Not yet done — requires you to authorise it.** Steps, once you're ready:

1. Push this repository to GitHub (`git remote add origin <your-repo-url>`, then
   `git push -u origin master`). No remote is configured yet — see the main README
   for the exact commands and a GitHub CLI option.
2. The public dataset (`data/public/*.csv`) is already committed (see above) — no
   extra step needed here. Regenerate + commit again only when the pipeline changes.
3. Go to [share.streamlit.io](https://share.streamlit.io), sign in with your GitHub
   account, and click "New app".
4. Repository: your pushed repo. Branch: `master`. Main file path:
   `dashboards/streamlit/app.py`.
5. Streamlit Cloud finds `dashboards/streamlit/requirements.txt` automatically —
   verified directly against Streamlit's own docs: it searches the entrypoint's
   directory first, then the repo root, so a requirements.txt co-located with
   `app.py` (as here) takes precedence.
6. Under "Advanced settings" -> "Secrets", optionally set:
   ```toml
   GITHUB_REPO_URL = "https://github.com/<you>/<repo>"
   CASE_STUDY_URL = "<link to your published case study, if any>"
   ```
   (Both are read via `os.environ` in `streamlit_lib/config.py` — Streamlit Cloud
   exposes Secrets as environment variables. Neither is a real secret; there's
   nothing sensitive to protect since the app never touches a database.)
7. Deploy. Once you have a live URL, verify it yourself by opening it — I cannot open
   or verify a URL on your behalf, so **do not consider the app "deployed" for
   portfolio purposes until you've confirmed the live URL actually works**.

### Known hosting limitations

- Streamlit Community Cloud's free tier has resource limits (1 GB RAM, shared CPU) —
  this app's largest table (`product_monthly_trend.csv`, ~1.8 MB, 34,068 rows) is
  well within that, but hasn't been load-tested under concurrent users.
- The app goes to sleep after a period of inactivity on the free tier and takes a
  few seconds to wake on the next visit — expected free-tier behaviour, not a bug.
- No auto-refresh from PostgreSQL: the deployed app only ever serves whatever CSVs
  were committed at deploy time. Refreshing the data means regenerating the CSVs
  locally, committing them, and pushing — there is no live database behind the public
  deployment by design (see the brief's "must not require a continuously running
  PostgreSQL database").
