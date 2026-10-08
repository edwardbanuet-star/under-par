# Under Par: setup guide

A static site (`index.html`) that reads `prices.json`. A script (`scripts/update_prices.py`) fills that file from SerpApi's Google Shopping API, and a GitHub Action runs it every day. All of it fits inside free tiers (confirm current limits at serpapi.com/pricing and github.com/pricing).

## How it fits together

```
products.json  -->  update_prices.py  -->  prices.json  -->  index.html
 (your watchlist)    (runs daily on          (the data)        (the website)
                      GitHub Actions)
```

## Step 1. Get a SerpApi key (5 minutes)

1. Go to https://serpapi.com and sign up for the free plan (250 searches/month at the time of writing).
2. Verify your email, and your phone number if asked.
3. Open your dashboard and copy your **API key**. Treat it like a password.

## Step 2. Test the script on your computer (10 minutes)

You need Python 3.8 or newer (check with `python3 --version`).

```bash
cd under-par
export SERPAPI_KEY="paste_your_key_here"      # Windows PowerShell: $env:SERPAPI_KEY="..."
MAX_SEARCHES=1 python3 scripts/update_prices.py --debug
```

This uses **1 search**. `--debug` prints every raw result, so you can see what Google returned and why items were kept or dropped. When it works, `prices.json` now holds real data.

View the site locally:

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000. (Opening `index.html` by double-click won't work, because browsers block reading `prices.json` from a file.)

## Step 3. Put the project on GitHub (10 minutes)

1. Create a free account at https://github.com, then click **New repository** (name it `under-par`, public is fine).
2. Upload everything in this folder, including the hidden `.github` folder. The easiest way is GitHub Desktop, or `git init` / `git add .` / `git commit` / `git push` from the command line.
3. Do **not** commit your API key. It goes in a secret (next step).

## Step 4. Add your key as a secret

1. In your repo: **Settings > Secrets and variables > Actions > New repository secret**.
2. Name: `SERPAPI_KEY`. Value: your key. Save.

## Step 5. Run the daily job once by hand

1. Open the **Actions** tab. If asked, enable workflows.
2. Choose **Update prices** on the left, then **Run workflow**.
3. After a minute or two, `prices.json` in your repo should update with a commit from `price-bot`. If the run shows a red X, open it and read the log.

After that it runs on its own every day (09:17 UTC).

## Step 6. Publish the site

1. **Settings > Pages**. Under "Build and deployment", pick **Deploy from a branch**, branch `main`, folder `/ (root)`, then Save.
2. In a minute or so your site is live at `https://YOUR-USERNAME.github.io/under-par/`.
3. If `prices.json` updates in the repo but the live site doesn't change, check the Actions tab for the "pages build and deployment" run.

## Step 7. Tune your watchlist

Edit `products.json` to add or change products. Each entry has:

| Field | What it does |
|---|---|
| `query` | The Google Shopping search text |
| `par` | List price (MSRP), used for "under par" math |
| `must_include` | Words every result title must contain (cuts out wrong products) |
| `exclude` | Words that disqualify a result (headcovers, used, kids, etc.) |
| `min_price` | Drops results below this price (cases, accessories, scams) |

If a product shows no offers, run with `--debug` and loosen `must_include` or `min_price`.

## Keep an eye on your search budget

- Each product search costs 1 search. The script refreshes up to `MAX_SEARCHES` (8) of the **least recently updated** products per run.
- 8 per day x 30 days = 240, just under the 250 free searches.
- With 10 products, each is refreshed about every 1 to 2 days. With 100 products, each would refresh about every 12 days. Add products slowly, or upgrade your plan.
- Your SerpApi dashboard shows searches used this month. Manual test runs count too.

## Known limits

- Google Shopping returns a mix of stores, and shipping cost is often missing. The site only shows "free shipping" when the result says so.
- Links come from Google's results. Once you join retailer affiliate programs, you can replace them with your tracking links.
- Prices can be stale or change before a visitor clicks. The page says so; keep that wording.
- Field names in SerpApi's response can change. If the script suddenly finds nothing, run `--debug` and check the SerpApi docs for Google Shopping.
