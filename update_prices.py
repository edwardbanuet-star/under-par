#!/usr/bin/env python3
"""Refresh prices.json from SerpApi's Google Shopping API.

Reads products.json, searches the products that were updated longest ago
(up to MAX_SEARCHES per run so you stay inside the free plan), and writes prices.json.
No third-party packages needed.

Usage:
  SERPAPI_KEY=your_key python /update_prices.py [--debug]
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "products.json"
OUT = ROOT / "prices.json"
API = "https://serpapi.com/search.json"
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES", "8"))  # 8/day is about 240/month
KEEP = 6  # offers kept per product
DEBUG = "--debug" in sys.argv


def search(query, key):
    params = {"engine": "google_shopping", "q": query, "gl": "us", "hl": "en", "api_key": key}
    with urllib.request.urlopen(API + "?" + urllib.parse.urlencode(params), timeout=60) as r:
        return json.load(r)


def offers_from(data, p):
    """Turn raw shopping results into a short, filtered, one-per-store offer list."""
    best = {}
    for r in data.get("shopping_results", []):
        title = (r.get("title") or "").lower()
        store = r.get("source")
        price = r.get("extracted_price")
        if DEBUG:
            print("   ", price, "|", store, "|", r.get("title"))
        if not (title and store and isinstance(price, (int, float))):
            continue
        if r.get("second_hand_condition"):
            continue  # skip used items
        if price < p.get("min_price", 0):
            continue
        if any(w.lower() not in title for w in p.get("must_include", [])):
            continue
        if any(w.lower() in title for w in p.get("exclude", [])):
            continue
        offer = {
            "store": store,
            "price": round(float(price), 2),
            "link": r.get("link") or r.get("product_link") or "",
            "free_shipping": "free" in (r.get("delivery") or "").lower(),
        }
        if store not in best or offer["price"] < best[store]["price"]:
            best[store] = offer
    return sorted(best.values(), key=lambda o: o["price"])[:KEEP]


def main():
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        sys.exit("Set the SERPAPI_KEY environment variable first.")

    products = json.loads(PRODUCTS.read_text())["products"]
    old = {}
    if OUT.exists():
        try:
            old = {x["id"]: x for x in json.loads(OUT.read_text()).get("products", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    # Oldest (or never) updated first, so every product gets its turn.
    queue = sorted(products, key=lambda p: old.get(p["id"], {}).get("updated", ""))[:MAX_SEARCHES]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fresh = {}
    for p in queue:
        print("Searching:", p["query"])
        try:
            offers = offers_from(search(p["query"], key), p)
        except Exception as e:  # keep going; old data stays in place
            print("  failed:", e)
            continue
        if not offers:
            print("  no offers passed your filters (try --debug and loosen must_include/min_price)")
            continue
        fresh[p["id"]] = {"updated": now, "offers": offers}
        print("  kept", len(offers), "offers; best", offers[0]["price"], "at", offers[0]["store"])

    out_products = []
    for p in products:
        prev = old.get(p["id"], {})
        got = fresh.get(p["id"], {})
        out_products.append({
            "id": p["id"], "category": p["category"], "name": p["name"], "par": p["par"],
            "updated": got.get("updated", prev.get("updated", "")),
            "offers": got.get("offers", prev.get("offers", [])),
        })

    OUT.write_text(json.dumps({"updated_at": now, "sample": False, "products": out_products}, indent=2) + "\n")
    print("Wrote", OUT.name, "with", len(fresh), "refreshed products.")


if __name__ == "__main__":
    main()
