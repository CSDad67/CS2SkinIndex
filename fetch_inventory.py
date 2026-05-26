#!/usr/bin/env python3
"""
fetch_inventory.py — fetches the user's CS2 Steam inventory via GitHub Actions
and saves it as steam_inventory.json for the web app to import.

Usage: python3 fetch_inventory.py --steamid 76561198XXXXXXXXX
Or set STEAM_ID environment variable.
"""
import json, sys, os, urllib.request, urllib.parse, datetime, argparse

def fetch_inventory(steam_id, count=5000):
    """Fetch CS2 inventory from Steam. Works server-side (no CORS)."""
    url = (
        f"https://steamcommunity.com/inventory/{steam_id}/730/2"
        f"?l=english&count={count}"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; CS2SkinIndex/1.0)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
            return data
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"ERROR: Steam returned 403. Make sure your inventory is set to PUBLIC.")
            print(f"  Steam Profile → Edit Profile → Privacy Settings → Inventory = Public")
        raise

def parse_wear(market_hash_name):
    """Extract wear condition from market hash name."""
    for wear in ["Factory New","Minimal Wear","Field-Tested","Well-Worn","Battle-Scarred"]:
        if wear in market_hash_name:
            return wear
    return ""

def parse_float_from_descriptions(desc):
    """Try to extract float value from Steam item description tags."""
    # Steam embeds float in fraudwarnings or item_description sometimes
    for fw in (desc.get("fraudwarnings") or []):
        if "float" in fw.lower() or "wear rating" in fw.lower():
            import re
            m = re.search(r"[0-9]\.[0-9]{6,}", fw)
            if m:
                return m.group(0)
    return ""

def is_stattrak(market_hash_name):
    return "StatTrak" in market_hash_name or "StatTrak™" in market_hash_name

def convert_inventory(raw_data, steam_id):
    """Convert Steam inventory format to CS2SkinIndex import format."""
    assets       = raw_data.get("assets", [])
    descriptions = raw_data.get("descriptions", [])

    # Build description lookup by classid+instanceid
    desc_map = {}
    for d in descriptions:
        key = f"{d.get('classid','')}_{d.get('instanceid','')}"
        desc_map[key] = d

    # Group by market_hash_name (weapon+skin+wear)
    # We need to map back to case store keys
    # Format: store key = cs2_{CASE_SLUG}_inventory, skin key = sid(name)
    import re
    def sid(name):
        return re.sub(r'[^a-z0-9]', '_', name.lower())

    # Build entries grouped by skin base name (without wear)
    skin_entries = {}

    for asset in assets:
        key = f"{asset.get('classid','')}_{asset.get('instanceid','')}"
        desc = desc_map.get(key, {})
        mhn  = desc.get("market_hash_name", "")

        if not mhn or "730" not in str(desc.get("appid","730")):
            continue

        # Skip non-skin items (stickers, cases, keys, agents, etc.)
        # Weapon skins and knife skins have a '|'in their name
        # Gloves also have '|'
        if " | " not in mhn and not mhn.startswith("★"):
            continue

        wear     = parse_wear(mhn)
        float_v  = parse_float_from_descriptions(desc)
        st       = is_stattrak(mhn)

        # Base name without wear and without StatTrak prefix
        base = mhn
        if wear:
            base = base.replace(f" ({wear})", "").strip()
        if st:
            base = base.replace("StatTrak™ ", "").strip()

        skin_id = sid(base)

        if skin_id not in skin_entries:
            skin_entries[skin_id] = {
                "name":    base,
                "entries": [],
                "st":      st,
            }

        entry = {
            "st":      st,
            "wear":    wear,
            "float":   float_v,
            "pattern": "",
            "assetid": asset.get("assetid",""),
        }
        skin_entries[skin_id]["entries"].append(entry)

    return {
        "version":     3,
        "type":        "steam_inventory_import",
        "steam_id":    steam_id,
        "fetched":     datetime.datetime.utcnow().isoformat() + "Z",
        "total_items": len(skin_entries),
        "skin_entries": skin_entries,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steamid", default=os.environ.get("STEAM_ID",""))
    parser.add_argument("--output",  default="steam_inventory.json")
    args = parser.parse_args()

    if not args.steamid:
        print("ERROR: Steam ID required. Use --steamid or set STEAM_ID env var.")
        sys.exit(1)

    print(f"Fetching CS2 inventory for Steam ID: {args.steamid}")
    raw = fetch_inventory(args.steamid)

    total_assets = len(raw.get("assets", []))
    print(f"  Raw items in inventory: {total_assets}")

    converted = convert_inventory(raw, args.steamid)
    print(f"  CS2 weapon skins found: {converted['total_items']}")

    with open(args.output, "w") as f:
        json.dump(converted, f, indent=2)

    print(f"  Saved to {args.output}")

if __name__ == "__main__":
    main()
