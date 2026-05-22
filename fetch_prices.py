#!/usr/bin/env python3
"""
fetch_prices.py — run by GitHub Actions to update prices.json
Fetches Steam Community Market prices for all CS2 case items.
"""
import json, time, urllib.request, urllib.parse, datetime, sys, os

def fetch_price(market_hash_name):
    encoded = urllib.parse.quote(market_hash_name)
    url = (
        "https://steamcommunity.com/market/priceoverview/"
        f"?appid=730&currency=1&market_hash_name={encoded}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
            if data.get("success"):
                price = data.get("lowest_price") or data.get("median_price")
                volume = data.get("volume", "")
                return {"steam": price, "volume": volume}
    except Exception as e:
        pass
    return {"steam": None}

def main():
    config_path = "prices_config.json"
    output_path = "prices.json"

    if not os.path.exists(config_path):
        print(f"ERROR: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    hashes = config.get("hashes", [])
    print(f"Fetching prices for {len(hashes)} items...")

    results = {}
    delay = 0.85  # seconds between requests — respects Steam rate limit

    for i, h in enumerate(hashes):
        result = fetch_price(h)
        results[h] = result

        status = result["steam"] or "N/A"
        if (i + 1) % 100 == 0 or i == 0:
            print(f"  [{i+1}/{len(hashes)}] {h[:50]} → {status}")

        if i < len(hashes) - 1:
            time.sleep(delay)

    success = sum(1 for v in results.values() if v.get("steam"))
    print(f"\nComplete: {success}/{len(hashes)} prices found")

    output = {
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Steam Community Market",
        "currency": "USD",
        "total": len(results),
        "found": success,
        "prices": results,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    print(f"Saved to {output_path} ({os.path.getsize(output_path)//1024}KB)")

if __name__ == "__main__":
    main()
