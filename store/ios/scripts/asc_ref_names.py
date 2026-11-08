#!/usr/bin/env python3
"""Set the internal reference names in App Store Connect to English (in-app purchases, Game Center
achievements and leaderboards), taken from each item's en-US title. Players never see these names.
Changes nothing else and submits nothing."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from asc_publish import ASC, BUNDLE_ID

a = ASC()
aid = a.get("/v1/apps", **{"filter[bundleId]": BUNDLE_ID})["data"][0]["id"]

def en_name(locs, key="name"):
    for l in locs:
        if l["attributes"].get("locale") == "en-US":
            return (l["attributes"].get(key) or "").strip()
    return ""

for iap in a.all(f"/v1/apps/{aid}/inAppPurchasesV2", limit=200):
    at = iap["attributes"]
    en = en_name(a.all(f"/v2/inAppPurchases/{iap['id']}/inAppPurchaseLocalizations"))
    if not en or en == at.get("name"):
        print("IAP", at.get("productId"), "keep:", at.get("name")); continue
    try:
        a.call("PATCH", f"/v2/inAppPurchases/{iap['id']}", {"data": {"type": "inAppPurchases", "id": iap["id"], "attributes": {"name": en}}})
        print("IAP", at.get("productId"), ":", at.get("name"), "->", en)
    except RuntimeError as e:
        print("WARN IAP", at.get("productId"), str(e)[:300])

gcd = a.call("GET", f"/v1/apps/{aid}/gameCenterDetail", ok=(200, 404)).get("data")
if gcd:
    for kind, lockind in (("gameCenterAchievements", "localizations"), ("gameCenterLeaderboards", "localizations")):
        for it in a.all(f"/v1/gameCenterDetails/{gcd['id']}/{kind}", limit=200):
            at = it["attributes"]
            en = en_name(a.all(f"/v1/{kind}/{it['id']}/{lockind}", limit=50))
            if not en or en == at.get("referenceName"):
                print(kind, at.get("vendorIdentifier"), "keep:", at.get("referenceName")); continue
            try:
                a.call("PATCH", f"/v1/{kind}/{it['id']}", {"data": {"type": kind, "id": it["id"], "attributes": {"referenceName": en}}})
                print(kind, at.get("vendorIdentifier"), ":", at.get("referenceName"), "->", en)
            except RuntimeError as e:
                print("WARN", kind, at.get("vendorIdentifier"), str(e)[:300])
print("Done. Nothing submitted.")
