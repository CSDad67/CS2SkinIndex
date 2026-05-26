#!/usr/bin/env python3
"""
fetch_inventory.py - Fetches CS2 Steam inventory for CS2 Master Skin Index.
Always writes steam_inventory.json (even on error) so you can see what happened.
"""
import json, sys, os, time, re, argparse, datetime, traceback
import urllib.request, urllib.parse, urllib.error

OUTPUT_FILE = "steam_inventory.json"

def save_result(data):
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {OUTPUT_FILE}")

def save_error(message, steam_id="", extra={}):
    result = {
        "version":     3,
        "type":        "steam_inventory_error",
        "steam_id":    steam_id,
        "fetched":     datetime.datetime.utcnow().isoformat() + "Z",
        "error":       message,
        "total_items": 0,
        "skin_entries": {},
        **extra
    }
    save_result(result)
    print(f"\nERROR: {message}")
    return result

def fetch_inventory(steam_id):
    url = (
        f"https://steamcommunity.com/inventory/{steam_id}/730/2"
        f"?l=english&count=5000"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, text/javascript, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://steamcommunity.com/",
    }
    print(f"Fetching: {url}")
    
    for attempt in range(3):
        if attempt:
            wait = attempt * 3
            print(f"Retry {attempt}/2 in {wait}s...")
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                try:
                    import gzip
                    if r.info().get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                except Exception:
                    pass
                data = json.loads(raw.decode("utf-8"))
                return data, None
        except urllib.error.HTTPError as e:
            body = ""
            try: body = e.read().decode()[:200]
            except: pass
            if e.code == 403:
                return None, (
                    f"Steam returned 403 Forbidden. "
                    f"Your inventory MUST be set to Public: "
                    f"Steam > Profile > Edit Profile > Privacy Settings > Inventory = Public. "
                    f"Body: {body}"
                )
            elif e.code == 429:
                print(f"Rate limited (429), waiting 15s...")
                time.sleep(15)
                continue
            else:
                return None, f"HTTP {e.code}: {e.reason}. Body: {body}"
        except Exception as e:
            print(f"Attempt {attempt+1} error: {e}")
            last_err = str(e)
    
    return None, f"All retries failed. Last error: {last_err}"

def sid(name):
    return re.sub(r"[^a-z0-9]", "_", name.lower())

def convert(raw, steam_id):
    assets       = raw.get("assets", [])
    descriptions = raw.get("descriptions", [])
    
    print(f"Raw inventory: {len(assets)} assets, {len(descriptions)} descriptions")
    
    if not assets:
        keys = list(raw.keys())
        return None, (
            f"No assets found. Response keys: {keys}. "
            f"This usually means the inventory is private or empty."
        )
    
    desc_map = {}
    for d in descriptions:
        key = f"{d.get('classid','')}_{d.get('instanceid','')}"
        desc_map[key] = d
    
    skin_entries = {}
    skipped_keys = {"cases":0, "stickers":0, "keys":0, "agents":0, "other":0, "skins":0}
    
    for asset in assets:
        key  = f"{asset.get('classid','')}_{asset.get('instanceid','')}"
        desc = desc_map.get(key, {})
        mhn  = desc.get("market_hash_name", "")
        if not mhn:
            skipped_keys["other"] += 1
            continue
        
        # Categorise skip reasons for transparency
        if " | " not in mhn:
            if "Case" in mhn or "Package" in mhn:
                skipped_keys["cases"] += 1
            elif "Sticker" in mhn or "Patch" in mhn:
                skipped_keys["stickers"] += 1
            elif "Key" in mhn:
                skipped_keys["keys"] += 1
            elif "Agent" in mhn:
                skipped_keys["agents"] += 1
            else:
                skipped_keys["other"] += 1
            continue
        
        skipped_keys["skins"] += 1
        
        # Determine wear
        wear = ""
        for w in ["Factory New","Minimal Wear","Field-Tested","Well-Worn","Battle-Scarred"]:
            if f"({w})" in mhn:
                wear = w
                break
        
        st       = "StatTrak" in mhn
        souvenir = "Souvenir" in mhn
        
        # Build base name
        base = mhn
        if wear:
            base = base.replace(f" ({wear})", "").strip()
        if st:
            base = base.replace("StatTrak\u2122 ", "").replace("StatTrak ", "").strip()
        if souvenir:
            base = base.replace("Souvenir ", "").strip()
        
        skin_id = sid(base)
        if skin_id not in skin_entries:
            skin_entries[skin_id] = {"name": base, "entries": []}
        
        skin_entries[skin_id]["entries"].append({
            "st":       st,
            "souvenir": souvenir,
            "wear":     wear,
            "float":    "",
            "pattern":  "",
            "assetid":  asset.get("assetid", ""),
        })
    
    print(f"Categorised: {skipped_keys}")
    print(f"Unique weapon skins found: {len(skin_entries)}")
    
    return skin_entries, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steamid", default=os.environ.get("STEAM_ID",""))
    parser.add_argument("--output",  default=OUTPUT_FILE)
    args = parser.parse_args()
    
    global OUTPUT_FILE
    OUTPUT_FILE = args.output
    
    steam_id = args.steamid.strip()
    print(f"Steam ID provided: '{steam_id}'")
    print(f"Steam ID length:    {len(steam_id)}")
    print(f"All digits:         {steam_id.isdigit()}")
    
    # Validate Steam ID
    if not steam_id:
        save_error(
            "No Steam ID provided. Enter your 17-digit Steam ID when running the workflow.",
            extra={"help": "Find your Steam ID at https://steamidfinder.com"}
        )
        sys.exit(1)
    
    if not steam_id.isdigit():
        save_error(
            f"Steam ID '{steam_id}' contains non-digit characters. "
            f"Must be 17 digits only, e.g. 76561198012345678. "
            f"Find yours at https://steamidfinder.com",
            steam_id=steam_id
        )
        sys.exit(1)
    
    if len(steam_id) != 17:
        save_error(
            f"Steam ID '{steam_id}' is {len(steam_id)} digits but must be exactly 17. "
            f"Find your correct ID at https://steamidfinder.com",
            steam_id=steam_id
        )
        sys.exit(1)
    
    if not steam_id.startswith("7656119"):
        save_error(
            f"Steam ID '{steam_id}' doesn't start with 7656119 - may be incorrect. "
            f"Verify at https://steamidfinder.com",
            steam_id=steam_id
        )
        # Don't exit - try anyway
    
    # Fetch inventory
    raw, err = fetch_inventory(steam_id)
    if err:
        save_error(err, steam_id=steam_id)
        sys.exit(1)
    
    # Convert
    skin_entries, err = convert(raw, steam_id)
    if err:
        save_error(err, steam_id=steam_id)
        sys.exit(1)
    
    # Save success result
    result = {
        "version":      3,
        "type":         "steam_inventory_import",
        "steam_id":     steam_id,
        "fetched":      datetime.datetime.utcnow().isoformat() + "Z",
        "total_items":  len(skin_entries),
        "skin_entries": skin_entries,
        "note":         "Float values not available via Steam API - add manually on case pages",
    }
    save_result(result)
    
    print(f"\nSUCCESS: {len(skin_entries)} skins saved to {OUTPUT_FILE}")
    print("Next: open cs2_inventory_manager.html and click LOAD FROM GITHUB")

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        save_error(
            f"Unexpected error: {type(e).__name__}: {e}\n{traceback.format_exc()}",
        )
        sys.exit(1)
