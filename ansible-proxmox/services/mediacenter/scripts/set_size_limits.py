#!/usr/bin/env python3
"""
Script to enforce a maximum download size limit (e.g. 3 GB) across Servarr applications
(Radarr, Sonarr, and Whisparr) using Custom Formats and Quality Profiles.
"""

import os
import json
import urllib.request
import urllib.error

SERVICES = [
    {
        "name": "Radarr",
        "url": os.getenv("RADARR_URL", "http://127.0.0.1:7878"),
        "api_key": os.getenv("RADARR_API_KEY", ""),
        "max_size_gb": 3.0,
    },
    {
        "name": "Sonarr",
        "url": os.getenv("SONARR_URL", "http://127.0.0.1:8989"),
        "api_key": os.getenv("SONARR_API_KEY", ""),
        "max_size_gb": 3.0,
    },
    {
        "name": "Whisparr",
        "url": os.getenv("WHISPARR_URL", "http://127.0.0.1:6969"),
        "api_key": os.getenv("WHISPARR_API_KEY", ""),
        "max_size_gb": 3.0,
    },
]


def api_request(url, path, api_key, method="GET", data=None):
    full_url = f"{url.rstrip('/')}/api/v3/{path.lstrip('/')}"
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(full_url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP {e.code} for {full_url}: {error_msg}")


def configure_service(svc):
    name = svc["name"]
    url = svc["url"]
    key = svc["api_key"]
    max_gb = svc["max_size_gb"]
    cf_name = f"Over {int(max_gb) if max_gb.is_integer() else max_gb}GB"

    print(f"\n--- Configuring {name} ({url}) ---")
    if not key:
        print(f"Skipping {name}: No API key provided (set {name.upper()}_API_KEY environment variable)")
        return

    # 1. Check or create/update Custom Format
    custom_formats = api_request(url, "customformat", key)
    cf_id = None
    existing_cf = None

    for cf in custom_formats:
        if "Over" in cf.get("name", "") and "GB" in cf.get("name", ""):
            existing_cf = cf
            cf_id = cf["id"]
            break

    spec = {
        "name": f"Size > {int(max_gb) if max_gb.is_integer() else max_gb}GB",
        "implementation": "SizeSpecification",
        "negate": False,
        "required": True,
        "fields": [
            {"order": 0, "name": "min", "value": max_gb},
            {"order": 1, "name": "max", "value": 1000.0},
        ],
    }

    if existing_cf:
        existing_cf["name"] = cf_name
        existing_cf["specifications"] = [spec]
        updated = api_request(url, f"customformat/{cf_id}", key, method="PUT", data=existing_cf)
        print(f"Updated Custom Format '{cf_name}' (ID: {cf_id})")
    else:
        new_cf = {
            "name": cf_name,
            "includeCustomFormatWhenRenaming": False,
            "specifications": [spec],
        }
        created = api_request(url, "customformat", key, method="POST", data=new_cf)
        cf_id = created.get("id")
        print(f"Created Custom Format '{cf_name}' (ID: {cf_id})")

    # 2. Assign Custom Format to all Quality Profiles with score -10000 and minFormatScore = 0
    profiles = api_request(url, "qualityprofile", key)
    for p in profiles:
        p_id = p["id"]
        format_items = p.get("formatItems", [])
        found = False
        for item in format_items:
            if item.get("format") == cf_id:
                item["score"] = -10000
                found = True
        if not found:
            format_items.append({
                "format": cf_id,
                "name": cf_name,
                "score": -10000,
            })
        p["formatItems"] = format_items
        p["minFormatScore"] = 0

        api_request(url, f"qualityprofile/{p_id}", key, method="PUT", data=p)
        print(f"Profile '{p.get('name')}' (ID: {p_id}) -> Assigned '{cf_name}' (-10000 score, minFormatScore=0)")


def main():
    for svc in SERVICES:
        try:
            configure_service(svc)
        except Exception as e:
            print(f"Failed to configure {svc['name']}: {e}")


if __name__ == "__main__":
    main()
