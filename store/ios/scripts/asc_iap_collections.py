#!/usr/bin/env python3
"""Create the 5 cosmetic collection in-app purchases (non-consumable) in App Store Connect.

Safe to run again: it only fills in what is missing. It never submits anything for review
(the first review of these purchases goes with the next app version, on the user's word).
"""
import hashlib, os, sys, requests
sys.path.insert(0, os.path.dirname(__file__))
from asc_publish import ASC, BUNDLE_ID, ROOT

P = "com.onemorefloor.escape."
SHOTS = os.path.join(ROOT, "iap", "colecciones")
DESC_EN, DESC_ES = "4 cosmetic skins, one per hero. Looks only.", "4 aspectos, uno por héroe. Solo estética."
ITEMS = [
    ("col_cuerda", "Taller de cuerda", "Clockwork Workshop", "1.99", "1-paquetes.png", DESC_EN, DESC_ES),
    ("col_estrellas", "Polvo de estrellas", "Stardust", "1.99", "1-paquetes.png", DESC_EN, DESC_ES),
    ("col_brasa", "Brasa eterna", "Eternal Ember", "1.99", "1-paquetes.png", DESC_EN, DESC_ES),
    ("col_cristal", "Cristal vivo", "Living Crystal", "1.99", "2-pagina-2.png", DESC_EN, DESC_ES),
    ("col_todas", "Las 4 colecciones", "All 4 Collections", "4.99", "2-pagina-2.png",
     "All 16 collection skins. Looks only.", "Los 16 aspectos de colección. Solo estética."),
]
NOTE = ("Non-consumable cosmetic pack. Open SHOP > COLLECTIONS (third tab) on the title screen, pick the pack and tap BUY. "
        "It unlocks {n} skins (Velo, Kai, Nyx, Brisa); they only change the look, no gameplay effect. "
        "RESTORE PURCHASES in Settings restores it.")

a = ASC()
aid = a.get("/v1/apps", **{"filter[bundleId]": BUNDLE_ID})["data"][0]["id"]
terrs = None
for key, es, en, price, shot, den, des in ITEMS:
    pid = P + key
    try:
        found = a.get(f"/v1/apps/{aid}/inAppPurchasesV2", **{"filter[productId]": pid})["data"]
        if found:
            iap = found[0]; print(pid, "exists:", iap["attributes"].get("state"))
        else:
            iap = a.call("POST", "/v2/inAppPurchases", {"data": {"type": "inAppPurchases", "attributes": {
                "name": es, "productId": pid, "inAppPurchaseType": "NON_CONSUMABLE", "familySharable": False,
                "reviewNote": NOTE.format(n=16 if key == "col_todas" else 4)},
                "relationships": {"app": {"data": {"type": "apps", "id": aid}}}}})["data"]
            print(pid, "created")
        iid = iap["id"]
        # localizations
        have = {l["attributes"]["locale"]: l for l in a.all(f"/v2/inAppPurchases/{iid}/inAppPurchaseLocalizations")}
        for loc, nm, ds in (("en-US", en, den), ("es-ES", es, des), ("es-MX", es, des)):
            if loc in have:
                a.call("PATCH", f"/v1/inAppPurchaseLocalizations/{have[loc]['id']}", {"data": {"type": "inAppPurchaseLocalizations",
                    "id": have[loc]["id"], "attributes": {"name": nm, "description": ds}}})
            else:
                a.call("POST", "/v1/inAppPurchaseLocalizations", {"data": {"type": "inAppPurchaseLocalizations",
                    "attributes": {"locale": loc, "name": nm, "description": ds},
                    "relationships": {"inAppPurchaseV2": {"data": {"type": "inAppPurchases", "id": iid}}}}})
        print("  localizations en-US es-ES es-MX ok")
        # price (base USA, Apple derives the other storefronts)
        sched = a.call("GET", f"/v2/inAppPurchases/{iid}/iapPriceSchedule", ok=(200, 404)).get("data")
        if not sched:
            pts = a.all(f"/v2/inAppPurchases/{iid}/pricePoints", **{"filter[territory]": "USA", "limit": 200})
            pt = next(p for p in pts if p["attributes"]["customerPrice"] in (price, price + "0"))
            a.call("POST", "/v1/inAppPurchasePriceSchedules", {"data": {"type": "inAppPurchasePriceSchedules", "relationships": {
                "inAppPurchase": {"data": {"type": "inAppPurchases", "id": iid}},
                "baseTerritory": {"data": {"type": "territories", "id": "USA"}},
                "manualPrices": {"data": [{"type": "inAppPurchasePrices", "id": "${p0}"}]}}},
                "included": [{"type": "inAppPurchasePrices", "id": "${p0}", "attributes": {"startDate": None},
                              "relationships": {"inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": pt["id"]}}}}]})
            print("  price", price, "USD set")
        else:
            print("  price already set")
        # availability: every territory
        if not a.call("GET", f"/v2/inAppPurchases/{iid}/inAppPurchaseAvailability", ok=(200, 404)).get("data"):
            terrs = terrs or [t["id"] for t in a.all("/v1/territories", limit=200)]
            a.call("POST", "/v1/inAppPurchaseAvailabilities", {"data": {"type": "inAppPurchaseAvailabilities",
                "attributes": {"availableInNewTerritories": True}, "relationships": {
                    "inAppPurchase": {"data": {"type": "inAppPurchases", "id": iid}},
                    "availableTerritories": {"data": [{"type": "territories", "id": t} for t in terrs]}}}})
            print("  availability: all", len(terrs), "territories")
        # review screenshot (the shop tab)
        data = open(os.path.join(SHOTS, shot), "rb").read(); md5 = hashlib.md5(data).hexdigest()
        cur = a.call("GET", f"/v2/inAppPurchases/{iid}/appStoreReviewScreenshot", ok=(200, 404)).get("data")
        if cur and cur["attributes"].get("sourceFileChecksum") == md5:
            print("  review screenshot unchanged")
        else:
            if cur:
                a.call("DELETE", f"/v1/inAppPurchaseAppStoreReviewScreenshots/{cur['id']}")
            obj = a.call("POST", "/v1/inAppPurchaseAppStoreReviewScreenshots", {"data": {"type": "inAppPurchaseAppStoreReviewScreenshots",
                "attributes": {"fileName": shot, "fileSize": len(data)},
                "relationships": {"inAppPurchaseV2": {"data": {"type": "inAppPurchases", "id": iid}}}}})["data"]
            for op in obj["attributes"]["uploadOperations"]:
                h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
                r = requests.request(op["method"], op["url"], headers=h, data=data[op["offset"]: op["offset"] + op["length"]], timeout=300)
                if r.status_code >= 300:
                    raise RuntimeError(f"upload part failed {r.status_code} {r.text[:300]}")
            a.call("PATCH", f"/v1/inAppPurchaseAppStoreReviewScreenshots/{obj['id']}", {"data": {"type": "inAppPurchaseAppStoreReviewScreenshots",
                "id": obj["id"], "attributes": {"uploaded": True, "sourceFileChecksum": md5}}})
            print("  review screenshot uploaded:", shot)
        st = a.call("GET", f"/v2/inAppPurchases/{iid}")["data"]["attributes"].get("state")
        print("  state now:", st)
    except Exception as e:
        print("ERROR", pid, str(e)[:1200])
print("Done. Nothing submitted for review.")
