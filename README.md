# COA — Condo Owners Alliance
Complete starter codebase. Follow the steps in order; no prior setup assumed.

## What is in this package
This repository is already laid out for direct Vercel deployment (static site at the
root + `api/` serverless functions). See `SETUP.md` (PT-BR) for the operational guide.

| File | Purpose |
|---|---|
| `index.html` (landing) and `app.html` (application) | The full application front end. English default, Spanish option. Three entry doors, guided triage with a free-text field routed by AI, budget upload and line-by-line analysis, official-records letter generators (letters always in English). |
| `api/analyze.js` | Serverless function (Vercel). Keeps the Anthropic API key on the server and relays analysis requests (model: `claude-opus-4-8`). |
| `vercel.json`, `.vercelignore` | Function timeout + keeps db/scripts/data out of the public deploy. |
| `db/COA_schema.sql` | Full Postgres data model for Supabase: associations, users, units, cases, timeline events, documents, budget analyses, association metrics, row-level security. v2.2 adds the unique indexes the idempotent import relies on. |
| `scripts/import_dbpr.py` | Initial data load from the real DBPR extracts (verified July 2026): condo registry + payment history + SIRS + Sunbiz enrichment. Supabase mode or `--local` SQLite mode (no credentials needed). |
| `scripts/check_supabase.py` | Verifies SUPABASE_URL/SERVICE_KEY and that all schema tables exist (stdlib only). |
| `scripts/dev_server.py` | Local test server mirroring `/api/analyze` (real or `COA_MOCK=1` mode). |
| `scripts/make_fixture_pdf.py`, `fixtures/budget_sample.pdf` | Sample budget PDF (with a deliberate math error) for end-to-end testing. |

## Deploy — step by step
1. **Supabase** (database + auth + file storage)
   1. Create a free project at supabase.com
   2. Open SQL Editor, paste `db/COA_schema.sql`, run it
   3. Authentication → enable Email (magic link recommended)
   4. Storage → create bucket `documents` (private)
   5. Verify: `python3 scripts/check_supabase.py`
2. **Vercel** (hosting)
   1. Push this repository to GitHub (it is already a git repo with the right layout)
   2. Import the repository at vercel.com → deploy (no build settings needed)
   3. Project Settings → Environment Variables → add `ANTHROPIC_API_KEY` (from console.anthropic.com)
   4. Note: `vercel.json` sets a 300s timeout for `api/analyze.js`; if your plan rejects it, lower `maxDuration` to 60
3. **Initial data**
   1. `pip install supabase pandas requests`
   2. `export SUPABASE_URL=... SUPABASE_SERVICE_KEY=...`
   3. `python3 scripts/import_dbpr.py download`
   4. `python3 scripts/import_dbpr.py condos && python3 scripts/import_dbpr.py payments`
   5. SIRS/Sunbiz when you have the files: `python3 scripts/import_dbpr.py sirs <file> 2025-07+` / `python3 scripts/import_dbpr.py sunbiz <file>`
   (To rehearse without Supabase: add `--local coa_local.db` to any import command.)

## How the budget analysis works (spec section 2)
The prompt embedded in `index.html` enforces, in order: arithmetic validation of every section total (V1–V4) before any finding; line-by-line variance with the calculation shown; the finding rules F1–F10 (one-time revenue, reserve projections, prevention-versus-repair swaps, generic lines, implausible unit-based revenue, deficit lines, cover-letter claims tested against the spreadsheet). Every figure in the output must exist in the document or be an arithmetic result of figures that do. Output language follows the user's UI language; generated legal letters are always English. The report always ends with the fixed disclaimer.

## Deliberately not in phase 1
Payments/subscriptions, native apps, automated election (C) and meetings (D) modules — these enter as manually handled cases. See `COA_Especificacao_SaaS_v2.md` for the full specification.

## Local test without deployment
Run `python3 scripts/dev_server.py` (with `ANTHROPIC_API_KEY` exported for real analyses, or `COA_MOCK=1` for a canned response) and open http://localhost:8000/app.html — this exercises the exact same `/api/analyze` path the Vercel deploy uses. Uploaded PDFs are limited to ~3 MB combined (Vercel's request-body cap); the app warns the user before sending.

## Data sources — verified URLs (v2.1)
No API keys required. All files below are free public downloads, updated weekly by DBPR.

Condominium registries (5 CSVs, all counties):
- https://www2.myfloridalicense.com/sto/file_download/extracts/Condo_MD.csv (Dade, Monroe)
- https://www2.myfloridalicense.com/sto/file_download/extracts/condo_PB.csv (Broward, Palm Beach)
- https://www2.myfloridalicense.com/sto/file_download/extracts/condo_CE.csv (Central East)
- https://www2.myfloridalicense.com/sto/file_download/extracts/Condo_CW.csv (Central West)
- https://www2.myfloridalicense.com/sto/file_download/extracts/Condo_NF.csv (North Florida)

Payment history (state annual fees, 5 years, by project letter): paymenthist_8002A/D/J/P/S/V.csv at the same base URL.

SIRS reporting database (which associations filed the structural reserve study):
https://www2.myfloridalicense.com/condos-timeshares-mobile-homes/condominiums-and-cooperatives-sirs-reporting/

CTMH complaint history per association — requires a Chapter 119 public records request:
submit via https://www2.myfloridalicense.com/contact-us/ (request text provided in the spec).

### One-command load order
```
python3 scripts/import_dbpr.py download
python3 scripts/import_dbpr.py condos
python3 scripts/import_dbpr.py payments
python3 scripts/import_dbpr.py sirs sirs_after_jul2025.csv 2025-07+
python3 scripts/import_dbpr.py sunbiz sunbiz_quarterly.csv
```
Verified against the real extracts (July 2026): 27,951 associations statewide,
23,802 managing entities, 140,954 payment rows (96% matched to a registered condo).
The import is idempotent — re-running upserts by DBPR Project Number.

## Custom domain — condoownersalliance.com
The production domain is **www.condoownersalliance.com**.
1. In Vercel: Project → Settings → Domains → add `condoownersalliance.com` and `www.condoownersalliance.com`.
2. At the current domain registrar/host: point DNS as Vercel instructs (A record `76.76.21.21` for the apex, CNAME `cname.vercel-dns.com` for `www`). Whatever page is currently live will be replaced once DNS propagates — export/back it up first if you want to keep it.
3. In Supabase: Authentication → URL Configuration → set Site URL to `https://www.condoownersalliance.com` (required for magic-link emails to redirect correctly).
4. Landing (`index.html`) already carries the canonical and Open Graph tags for this domain.
