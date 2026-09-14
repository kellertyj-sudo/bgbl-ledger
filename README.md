# BGBL Ledger

Static site for the BGBL keeper salary ledger. No build step, no dependencies.

## Contents

- `index.html` — the whole site, self-contained
- `csv/` — per-team rosters, league-wide roster, and the transaction log

## Publishing

### Option A — Netlify Drop (fastest)
1. Go to https://app.netlify.com/drop
2. Drag this entire folder onto the page
3. You get a public URL immediately

Create a free account to keep the URL stable across re-drops.

### Option B — GitHub Pages
1. Create a new **public** repo (e.g. `bgbl-ledger`)
2. Upload `index.html` and the `csv/` folder
3. Settings → Pages → Source: *Deploy from a branch* → `main` / `/ (root)`
4. Site appears at `https://<username>.github.io/bgbl-ledger/`

GitHub Pages needs a public repo on the free plan. The league data is fantasy rosters,
but `index.html` carries `<meta name="robots" content="noindex">` so search engines skip it.

## Updating

Regenerate `index.html` and `csv/` from the ledger, then re-upload. Nothing else changes.
