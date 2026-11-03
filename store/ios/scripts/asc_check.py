"""Read-only readiness check of the App Store page of One More Floor Escape (changes nothing)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from asc_publish import ASC, BUNDLE_ID, IAP_ID

a = ASC()
def safe(label, fn):
    try:
        fn()
    except Exception as e:
        print(f"[?] {label}: {str(e)[:400]}")

app = a.get("/v1/apps", **{"filter[bundleId]": BUNDLE_ID})["data"][0]; aid = app["id"]
print("APP", app["attributes"].get("name"), aid, "contentRights:", app["attributes"].get("contentRightsDeclaration"))

def version():
    vs = a.get(f"/v1/apps/{aid}/appStoreVersions", **{"filter[platform]": "IOS", "limit": 5})["data"]
    for v in vs:
        at = v["attributes"]; print("VERSION", at["versionString"], at.get("appStoreState") or at.get("appVersionState"), "release:", at.get("releaseType"))
    v = next(v for v in vs if v["attributes"]["versionString"] == "1.0.0")
    b = a.call("GET", f"/v1/appStoreVersions/{v['id']}/build").get("data")
    print("  attached build:", b and b["attributes"]["version"])
    rd = a.call("GET", f"/v1/appStoreVersions/{v['id']}/appStoreReviewDetail").get("data")
    if rd:
        at = rd["attributes"]; print("  review contact:", all(at.get(k) for k in ("contactFirstName", "contactLastName", "contactPhone", "contactEmail")))
    try:
        gc = a.call("GET", f"/v1/appStoreVersions/{v['id']}/gameCenterAppVersion").get("data")
        print("  game center on version:", bool(gc), gc and gc["attributes"])
    except Exception as e:
        print("  game center on version: ?", str(e)[:200])
    globals()["VID"] = v["id"]
safe("version", version)

def builds():
    bs = a.get("/v1/builds", **{"filter[app]": aid, "sort": "-uploadedDate", "limit": 12, "include": "preReleaseVersion"})
    pre = {i["id"]: i["attributes"]["version"] for i in bs.get("included", [])}
    for b in bs["data"]:
        pv = pre.get(b["relationships"]["preReleaseVersion"]["data"]["id"], "?")
        print("BUILD", pv, b["attributes"]["version"], b["attributes"]["processingState"], "expired" if b["attributes"].get("expired") else "")
safe("builds", builds)

safe("app price", lambda: print("APP PRICE schedule:", bool(a.call("GET", f"/v1/apps/{aid}/appPriceSchedule").get("data"))))
def avail():
    d = a.call("GET", f"/v1/apps/{aid}/appAvailabilityV2").get("data")
    print("AVAILABILITY:", d and d["attributes"])
safe("availability", avail)
def age():
    info = a.all(f"/v1/apps/{aid}/appInfos")[0]
    ar = a.get(f"/v1/appInfos/{info['id']}/ageRatingDeclaration")["data"]["attributes"]
    print("AGE RATING violenceCartoonOrFantasy:", ar.get("violenceCartoonOrFantasy"), "| appInfo state:", info["attributes"].get("appStoreState") or info["attributes"].get("state"))
safe("age", age)

def iap():
    ii = a.get(f"/v1/apps/{aid}/inAppPurchasesV2", **{"filter[productId]": IAP_ID})["data"]
    if not ii: print("IAP missing"); return
    i = ii[0]; at = i["attributes"]; print("IAP", at.get("productId"), at.get("inAppPurchaseType"), "state:", at.get("state"), "reviewNote:", bool(at.get("reviewNote")))
    for path, label in (("inAppPurchaseLocalizations", "localizations"), ("iapPriceSchedule", "price schedule"), ("inAppPurchaseAvailability", "availability"), ("appStoreReviewScreenshot", "review screenshot")):
        try:
            d = a.call("GET", f"/v2/inAppPurchases/{i['id']}/{path}").get("data")
            if isinstance(d, list): print(f"  {label}:", [(x["attributes"].get("locale"), x["attributes"].get("name"), x["attributes"].get("state")) for x in d])
            else: print(f"  {label}:", bool(d), d and {k: v for k, v in d["attributes"].items() if k in ("availableInNewTerritories", "assetDeliveryState", "fileName")})
        except Exception as e:
            print(f"  {label}: ?", str(e)[:200])
safe("iap", iap)

def gc():
    d = a.call("GET", f"/v1/apps/{aid}/gameCenterDetail").get("data")
    if not d: print("GAME CENTER: not enabled"); return
    ach = a.all(f"/v1/gameCenterDetails/{d['id']}/gameCenterAchievements")
    lbs = a.all(f"/v1/gameCenterDetails/{d['id']}/gameCenterLeaderboards")
    print("GAME CENTER achievements:", len(ach), "leaderboards:", len(lbs))
    noimg = noloc = 0
    for x in ach:
        locs = a.all(f"/v1/gameCenterAchievements/{x['id']}/localizations")
        if not locs: noloc += 1; continue
        for l in locs[:1]:
            img = a.call("GET", f"/v1/gameCenterAchievementLocalizations/{l['id']}/gameCenterAchievementImage").get("data")
            if not img: noimg += 1
    print("  achievements without localization:", noloc, "| without image (first locale):", noimg)
    for x in lbs:
        locs = a.all(f"/v1/gameCenterLeaderboards/{x['id']}/localizations")
        print("  leaderboard", x["attributes"].get("vendorIdentifier"), "locales:", len(locs))
safe("game center", gc)
print("CHECK DONE")
