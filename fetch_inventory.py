#!/usr/bin/env python3
"""
fetch_inventory.py - Fetches CS2 Steam inventory for CS2 Master Skin Index.
Always writes steam_inventory.json (even on error) so you can see what happened.
"""
import json, sys, os, time, re, argparse, datetime, traceback
import urllib.request, urllib.error

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {path} ({os.path.getsize(path)} bytes)")

def make_error(message, steam_id="", extra=None):
    result = {
        "version":      3,
        "type":         "steam_inventory_error",
        "steam_id":     steam_id,
        "fetched":      datetime.datetime.utcnow().isoformat() + "Z",
        "error":        message,
        "total_items":  0,
        "skin_entries": {}
    }
    if extra:
        result.update(extra)
    return result

def fetch_inventory(steam_id):
    url = (
        "https://steamcommunity.com/inventory/" + steam_id + "/730/2"
        "?l=english&count=5000"
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
    print("Fetching: " + url)

    last_err = "No attempts made"
    for attempt in range(3):
        if attempt > 0:
            wait = attempt * 4
            print("Retry " + str(attempt) + "/2 in " + str(wait) + "s...")
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
                return json.loads(raw.decode("utf-8")), None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:300]
            except Exception:
                pass
            if e.code == 403:
                return None, (
                    "Steam returned 403 Forbidden. "
                    "Set your inventory to PUBLIC: "
                    "Steam > Profile > Edit Profile > Privacy Settings > Inventory = Public. "
                    "Response body: " + body
                )
            elif e.code == 401:
                return None, (
                    "Steam returned 401 Unauthorized. "
                    "Inventory is private. Set to Public in Steam Privacy Settings."
                )
            elif e.code == 429:
                print("Rate limited (429), waiting 15s...")
                time.sleep(15)
                last_err = "Rate limited"
            else:
                last_err = "HTTP " + str(e.code) + ": " + str(e.reason) + " Body: " + body
                print(last_err)
        except Exception as e:
            last_err = str(e)
            print("Error on attempt " + str(attempt + 1) + ": " + last_err)

    return None, "All retries failed. Last error: " + last_err

def skin_id(name):
    return re.sub(r"[^a-z0-9]", "_", name.lower())

def convert_inventory(raw, steam_id):
    assets       = raw.get("assets", [])
    descriptions = raw.get("descriptions", [])

    print("Raw assets:       " + str(len(assets)))
    print("Raw descriptions: " + str(len(descriptions)))

    if not assets:
        return None, (
            "No assets in response. Keys in response: " + str(list(raw.keys())) + ". "
            "This usually means inventory is private or empty."
        )

    desc_map = {}
    for d in descriptions:
        key = str(d.get("classid","")) + "_" + str(d.get("instanceid",""))
        desc_map[key] = d

    skin_entries = {}
    counts = {"skins": 0, "cases": 0, "stickers": 0, "keys": 0, "other": 0}

    for asset in assets:
        key  = str(asset.get("classid","")) + "_" + str(asset.get("instanceid",""))
        desc = desc_map.get(key, {})
        mhn  = desc.get("market_hash_name", "")

        if not mhn:
            counts["other"] += 1
            continue

        if " | " not in mhn:
            if any(w in mhn for w in ["Case", "Package", "Capsule"]):
                counts["cases"] += 1
            elif any(w in mhn for w in ["Sticker", "Patch", "Graffiti"]):
                counts["stickers"] += 1
            elif "Key" in mhn:
                counts["keys"] += 1
            else:
                counts["other"] += 1
            continue

        counts["skins"] += 1

        wear = ""
        for w in ["Factory New","Minimal Wear","Field-Tested","Well-Worn","Battle-Scarred"]:
            if "(" + w + ")" in mhn:
                wear = w
                break

        st       = "StatTrak" in mhn
        souvenir = "Souvenir" in mhn

        base = mhn
        if wear:
            base = base.replace(" (" + wear + ")", "").strip()
        base = base.replace("StatTrak\u2122 ", "").replace("StatTrak ", "")
        base = base.replace("Souvenir ", "").strip()

        sid = skin_id(base)
        if sid not in skin_entries:
            skin_entries[sid] = {"name": base, "entries": []}

        skin_entries[sid]["entries"].append({
            "st":       st,
            "souvenir": souvenir,
            "wear":     wear,
            "float":    "",
            "pattern":  "",
            "assetid":  asset.get("assetid", ""),
        })

    print("Item counts: " + str(counts))
    print("Unique skins found: " + str(len(skin_entries)))
    return skin_entries, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steamid", default=os.environ.get("STEAM_ID", ""))
    parser.add_argument("--output",  default="steam_inventory.json")
    args = parser.parse_args()

    out  = args.output
    sid  = args.steamid.strip()

    print("Steam ID provided: '" + sid + "'")
    print("Length: " + str(len(sid)) + "  All digits: " + str(sid.isdigit()))

    # Validate
    if not sid:
        save_json(out, make_error(
            "No Steam ID provided. Enter your 17-digit Steam ID when running workflow.",
            extra={"help": "Find at https://steamidfinder.com"}
        ))
        sys.exit(1)

    if not sid.isdigit():
        save_json(out, make_error(
            "Steam ID '" + sid + "' contains non-digit characters. "
            "Must be 17 digits only. Find yours at https://steamidfinder.com",
            steam_id=sid
        ))
        sys.exit(1)

    if len(sid) != 17:
        save_json(out, make_error(
            "Steam ID is " + str(len(sid)) + " digits but must be exactly 17. "
            "Find your correct ID at https://steamidfinder.com",
            steam_id=sid
        ))
        sys.exit(1)

    # Fetch
    raw, err = fetch_inventory(sid)
    if err:
        save_json(out, make_error(err, steam_id=sid))
        sys.exit(1)

    # Convert
    skin_entries, err = convert_inventory(raw, sid)
    if err:
        save_json(out, make_error(err, steam_id=sid))
        sys.exit(1)

    # Save success
    result = {
        "version":      3,
        "type":         "steam_inventory_import",
        "steam_id":     sid,
        "fetched":      datetime.datetime.utcnow().isoformat() + "Z",
        "total_items":  len(skin_entries),
        "skin_entries": skin_entries,
        "note":         (
            "Float values not available via Steam API. "
            "Add them manually on individual case pages."
        ),
    }
    save_json(out, result)
    print("\nSUCCESS: " + str(len(skin_entries)) + " skins saved.")

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        try:
            save_json("steam_inventory.json", make_error(
                "Unexpected error: " + type(e).__name__ + ": " + str(e)
                + "\n" + traceback.format_exc()
            ))
        except Exception:
            pass
        sys.exit(1)
