#!/usr/bin/env python3
"""Fill the App Store page of One More Floor Escape through the App Store Connect API.

Uploads the text in store/ios/metadata/<locale>/, the screenshots in store/ios/screenshots/<locale>/,
the App Previews in store/ios/previews/<locale>/, sets categories and the age rating, and attaches the
newest processed build whose version matches. It only sends the version to App Review with --submit.

Needs the same secrets as the TestFlight workflow: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8 (env vars).
Optional: REVIEW_FIRST_NAME, REVIEW_LAST_NAME, REVIEW_PHONE, REVIEW_EMAIL for App Review contact details.
"""
import argparse, base64, hashlib, json, os, re, sys, time
import jwt, requests

API = "https://api.appstoreconnect.apple.com"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUNDLE_ID = "com.onemorefloor.escape"
# App Store locale codes for each metadata folder
LOCALES = {"en-US": "en-US", "es-ES": "es-ES", "es-MX": "es-MX"}
SHOT_TYPES = {"iphone": "APP_IPHONE_67", "ipad": "APP_IPAD_PRO_3GEN_129"}
MEDIA_FROM = {"es-MX": "es-ES"}  # Mexico uses the Spain screenshots and previews
IAP_ID = "com.onemorefloor.escape.full"  # non-consumable "Escape completo", created by the TestFlight workflow
PREVIEW_TYPES = {"iphone": "IPHONE_67", "ipad": "IPAD_PRO_3GEN_129"}



class _SameShot(Exception):
    pass

def p8():
    raw = os.environ["ASC_KEY_P8"].strip()
    if "BEGIN" not in raw:
        try:
            dec = base64.b64decode(re.sub(r"\s", "", raw)).decode()
            if "BEGIN" in dec:
                raw = dec
        except Exception:
            pass
    body = re.sub(r"[^A-Za-z0-9+/=]", "", re.sub(r"-----(BEGIN|END)[^-]*-----", "", raw))
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(body[i:i + 64] for i in range(0, len(body), 64)) + "\n-----END PRIVATE KEY-----\n"


class ASC:
    def __init__(self):
        self.key, self.kid, self.iss = p8(), os.environ["ASC_KEY_ID"].strip(), os.environ["ASC_ISSUER_ID"].strip()
        self.tok, self.exp = None, 0

    def token(self):
        if time.time() > self.exp - 60:
            self.exp = int(time.time()) + 15 * 60
            self.tok = jwt.encode({"iss": self.iss, "exp": self.exp, "aud": "appstoreconnect-v1"}, self.key,
                                  algorithm="ES256", headers={"kid": self.kid, "typ": "JWT"})
        return self.tok

    def call(self, method, path, body=None, params=None, ok=(200, 201, 204)):
        r = requests.request(method, path if path.startswith("http") else API + path, params=params,
                             headers={"Authorization": "Bearer " + self.token(), "Content-Type": "application/json"},
                             data=json.dumps(body) if body is not None else None, timeout=120)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:1500]}")
        return r.json() if r.text else {}

    def get(self, path, **params):
        return self.call("GET", path, params=params or None)

    def all(self, path, **params):
        out, nxt = [], None
        res = self.get(path, **params)
        while True:
            out += res.get("data", [])
            nxt = res.get("links", {}).get("next")
            if not nxt:
                return out
            res = self.call("GET", nxt)


def read(loc, name):
    f = os.path.join(ROOT, "metadata", loc, name + ".txt")
    if not os.path.exists(f):
        f = os.path.join(ROOT, "metadata", "default", name + ".txt")
    return open(f, encoding="utf-8").read().strip() if os.path.exists(f) else None


def upload_asset(a, kind, set_id, path, set_rel):
    """kind: appScreenshots | appPreviews. Reserve, PUT the parts, then commit with the MD5."""
    data = open(path, "rb").read()
    attrs = {"fileName": os.path.basename(path), "fileSize": len(data)}
    if kind == "appPreviews":
        attrs["mimeType"] = "video/mp4"
    res = a.call("POST", "/v1/" + kind, {"data": {"type": kind, "attributes": attrs,
                                                   "relationships": {set_rel: {"data": {"type": set_rel + "s", "id": set_id}}}}})
    obj = res["data"]
    for op in obj["attributes"]["uploadOperations"]:
        chunk = data[op["offset"]: op["offset"] + op["length"]]
        h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
        r = requests.request(op["method"], op["url"], headers=h, data=chunk, timeout=300)
        if r.status_code >= 300:
            raise RuntimeError(f"upload part failed {r.status_code} {r.text[:300]}")
    commit = {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}
    if kind == "appPreviews":
        commit["previewFrameTimeCode"] = "00:00:05:00"
    a.call("PATCH", f"/v1/{kind}/{obj['id']}", {"data": {"type": kind, "id": obj["id"], "attributes": commit}})
    return obj["id"]


def media(a, vloc_id, loc, folder, types, set_kind, set_type_attr, item_kind):
    base = os.path.join(ROOT, folder, loc)
    if not os.path.isdir(base):
        base = os.path.join(ROOT, folder, MEDIA_FROM.get(loc, loc))
    if not os.path.isdir(base):
        os.makedirs(base, exist_ok=True)  # empty folder: existing media of this kind gets cleared
    sets = {s["attributes"][set_type_attr]: s for s in a.all(f"/v1/appStoreVersionLocalizations/{vloc_id}/{set_kind}")}
    for dev, typ in types.items():
        files = sorted(f for f in os.listdir(base) if f.startswith(dev + "-"))
        s = sets.get(typ)
        if not files:  # nothing in the repo for this device: clear what the listing still shows
            if s:
                for old in a.all(f"/v1/{set_kind}/{s['id']}/{item_kind}"):
                    a.call("DELETE", f"/v1/{item_kind}/{old['id']}")
                print(f"  {loc} {typ}: cleared")
            continue
        if not s:
            s = a.call("POST", "/v1/" + set_kind, {"data": {"type": set_kind, "attributes": {set_type_attr: typ},
                "relationships": {"appStoreVersionLocalization": {"data": {"type": "appStoreVersionLocalizations", "id": vloc_id}}}}})["data"]
        for old in a.all(f"/v1/{set_kind}/{s['id']}/{item_kind}"):
            a.call("DELETE", f"/v1/{item_kind}/{old['id']}")
        rel = set_kind[:-1]  # appScreenshotSet / appPreviewSet
        for f in files:
            upload_asset(a, item_kind, s["id"], os.path.join(base, f), rel)
            print(f"  {loc} {typ}: {f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--no-media", action="store_true")
    ap.add_argument("--build", default="", help="exact build number to attach (default: newest valid)")
    ap.add_argument("--submit", action="store_true", help="send the version to App Review at the end")
    ap.add_argument("--cancel", action="store_true", help="only take the waiting submission back out of App Review")
    o = ap.parse_args()
    a = ASC()

    app = a.get("/v1/apps", **{"filter[bundleId]": BUNDLE_ID})["data"][0]
    aid = app["id"]
    print("App", app["attributes"]["name"], aid)
    if o.cancel:
        subs = a.get("/v1/reviewSubmissions", **{"filter[app]": aid, "filter[platform]": "IOS",
                                                  "filter[state]": "WAITING_FOR_REVIEW,IN_REVIEW,UNRESOLVED_ISSUES,READY_FOR_REVIEW"})["data"]
        for sub in subs:
            print("Submission", sub["id"], sub["attributes"].get("state"), sub["attributes"].get("submittedDate"))
            try:
                a.call("PATCH", f"/v1/reviewSubmissions/{sub['id']}", {"data": {"type": "reviewSubmissions", "id": sub["id"], "attributes": {"canceled": True}}})
                print("  canceled")
            except RuntimeError as e:
                print("  not canceled:", str(e)[:300])
        for v in a.all(f"/v1/apps/{aid}/appStoreVersions"):
            print("Version", v["attributes"].get("versionString"), v["attributes"].get("appStoreState"))
        if not subs:
            print("No submission to cancel")
        return

    # app info: categories, name, subtitle, privacy URL per locale
    infos = a.all(f"/v1/apps/{aid}/appInfos")
    LIVE = ("READY_FOR_SALE", "REPLACED_WITH_NEW_INFO", "READY_FOR_DISTRIBUTION", "ACCEPTED")
    print("App infos:", [(i["id"][:8], i["attributes"].get("state"), i["attributes"].get("appStoreState")) for i in infos])
    info = next((i for i in infos if i["attributes"].get("state") not in LIVE and i["attributes"].get("appStoreState") not in LIVE), infos[0])
    def cats(*subs):
        rel = {"primaryCategory": {"data": {"type": "appCategories", "id": "GAMES"}}}
        for n, c in zip(("primarySubcategoryOne", "primarySubcategoryTwo"), subs):
            rel[n] = {"data": {"type": "appCategories", "id": c}}
        a.call("PATCH", f"/v1/appInfos/{info['id']}", {"data": {"type": "appInfos", "id": info["id"], "relationships": rel}})
    for subs in (("GAMES_ACTION", "GAMES_ARCADE"), ("GAMES_ACTION",), ()):
        try:
            cats(*subs)
            print("Categories: Games", subs)
            break
        except RuntimeError as e:
            print("WARN categories", subs, str(e)[:200])
    ilocs = {l["attributes"]["locale"]: l for l in a.all(f"/v1/appInfos/{info['id']}/appInfoLocalizations")}
    for folder, loc in LOCALES.items():
        attrs = {k: v for k, v in {"name": read(folder, "name"), "subtitle": read(folder, "subtitle"),
                                   "privacyPolicyUrl": read(folder, "privacy_url")}.items() if v}
        try:  # a live app info is locked until a new version exists; the next run edits the new one
            if loc in ilocs:
                a.call("PATCH", f"/v1/appInfoLocalizations/{ilocs[loc]['id']}", {"data": {"type": "appInfoLocalizations", "id": ilocs[loc]["id"], "attributes": attrs}})
            else:
                a.call("POST", "/v1/appInfoLocalizations", {"data": {"type": "appInfoLocalizations", "attributes": {"locale": loc, **attrs},
                    "relationships": {"appInfo": {"data": {"type": "appInfos", "id": info["id"]}}}}})
            print("App info", loc, "ok")
        except RuntimeError as e:
            print("WARN app info", loc, "(locked while live):", str(e)[:200])

    # content rights: uses third-party art (CC0 pack) with the rights to it
    try:
        a.call("PATCH", f"/v1/apps/{aid}", {"data": {"type": "apps", "id": aid, "attributes": {"contentRightsDeclaration": "USES_THIRD_PARTY_CONTENT"}}})
        print("Content rights declared")
    except RuntimeError as e:
        print("WARN content rights:", str(e)[:300])
    # price: free (the full game is the in-app purchase)
    try:
        pts = a.get(f"/v1/apps/{aid}/appPricePoints", **{"filter[territory]": "USA", "limit": 200})["data"]
        free = next(p for p in pts if float(p["attributes"]["customerPrice"]) == 0)
        a.call("POST", "/v1/appPriceSchedules", {"data": {"type": "appPriceSchedules", "relationships": {
            "app": {"data": {"type": "apps", "id": aid}},
            "baseTerritory": {"data": {"type": "territories", "id": "USA"}},
            "manualPrices": {"data": [{"type": "appPrices", "id": "${free}"}]}}},
            "included": [{"type": "appPrices", "id": "${free}", "attributes": {"startDate": None},
                          "relationships": {"appPricePoint": {"data": {"type": "appPricePoints", "id": free["id"]}}}}]})
        print("Price: Free")
    except (RuntimeError, StopIteration, KeyError) as e:
        print("WARN price:", str(e)[:300])

    # availability: every territory (app and in-app purchase)
    terrs = None
    try:
        terrs = [t["id"] for t in a.all("/v1/territories", limit=200)]
        if not a.call("GET", f"/v1/apps/{aid}/appAvailabilityV2", ok=(200, 404)).get("data"):
            a.call("POST", "/v2/appAvailabilities", {"data": {"type": "appAvailabilities", "attributes": {"availableInNewTerritories": True},
                "relationships": {"app": {"data": {"type": "apps", "id": aid}},
                                  "territoryAvailabilities": {"data": [{"type": "territoryAvailabilities", "id": "${" + t + "}"} for t in terrs]}}},
                "included": [{"type": "territoryAvailabilities", "id": "${" + t + "}", "attributes": {"available": True},
                              "relationships": {"territory": {"data": {"type": "territories", "id": t}}}} for t in terrs]})
            print("App availability: all", len(terrs), "territories")
        else:
            print("App availability already set")
    except RuntimeError as e:
        print("WARN app availability:", str(e)[:400])

    # age rating: only mild cartoon/fantasy violence
    try:
        ar = a.get(f"/v1/appInfos/{info['id']}/ageRatingDeclaration")["data"]
        attrs = {}
        LEVELS = ("alcoholTobaccoOrDrugUseOrReferences", "contests", "gamblingSimulated", "gunsOrOtherWeapons",
                  "horrorOrFearThemes", "matureOrSuggestiveThemes", "medicalOrTreatmentInformation",
                  "profanityOrCrudeHumor", "sexualContentGraphicAndNudity", "sexualContentOrNudity",
                  "violenceCartoonOrFantasy", "violenceRealistic", "violenceRealisticProlongedGraphicOrSadistic")
        SKIP = ("kidsAgeBand", "ageRatingOverride", "ageRatingOverrideV2", "koreaAgeRatingOverride", "developerAgeRatingInfoUrl")
        BOOLS = ("gambling", "lootBox", "unrestrictedWebAccess", "messagingAndChat", "userGeneratedContent", "advertising",
                 "parentalControls", "ageAssurance", "healthOrWellnessTopics", "socialMedia", "socialMediaAgeRestricted")
        for k, v in ar["attributes"].items():
            if k in SKIP:
                continue
            elif k == "violenceCartoonOrFantasy":
                attrs[k] = "INFREQUENT_OR_MILD"
            elif k in LEVELS:
                attrs[k] = "NONE"
            elif isinstance(v, bool) or k in BOOLS:
                attrs[k] = False
        a.call("PATCH", f"/v1/ageRatingDeclarations/{ar['id']}", {"data": {"type": "ageRatingDeclarations", "id": ar["id"], "attributes": attrs}})
        print("Age rating set (mild fantasy violence only)")
    except RuntimeError as e:
        print("WARN age rating, answer it in App Store Connect:", e)

    # the App Store version
    vers = a.all(f"/v1/apps/{aid}/appStoreVersions", **{"filter[platform]": "IOS"})
    ver = next((v for v in vers if v["attributes"]["versionString"] == o.version), None)
    editable = ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED", "INVALID_BINARY")
    if not ver:
        ver = next((v for v in vers if v["attributes"].get("appStoreState") in editable), None)
        if ver:
            a.call("PATCH", f"/v1/appStoreVersions/{ver['id']}", {"data": {"type": "appStoreVersions", "id": ver["id"], "attributes": {"versionString": o.version}}})
        else:
            ver = a.call("POST", "/v1/appStoreVersions", {"data": {"type": "appStoreVersions", "attributes": {"platform": "IOS", "versionString": o.version},
                "relationships": {"app": {"data": {"type": "apps", "id": aid}}}}})["data"]
    vid = ver["id"]
    a.call("PATCH", f"/v1/appStoreVersions/{vid}", {"data": {"type": "appStoreVersions", "id": vid, "attributes": {
        "copyright": read("default", "copyright"), "releaseType": "AFTER_APPROVAL"}}})
    print("Version", o.version, vid)

    vlocs = {l["attributes"]["locale"]: l for l in a.all(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations")}
    for folder, loc in LOCALES.items():
        attrs = {k: v for k, v in {"description": read(folder, "description"), "keywords": read(folder, "keywords"),
                                   "promotionalText": read(folder, "promotional_text"), "supportUrl": read(folder, "support_url"),
                                   "marketingUrl": read(folder, "marketing_url")}.items() if v}
        if o.version != "1.0.0" and read(folder, "whats_new"):  # Apple refuses release notes on the first version
            attrs["whatsNew"] = read(folder, "whats_new")
        if loc in vlocs:
            vl = a.call("PATCH", f"/v1/appStoreVersionLocalizations/{vlocs[loc]['id']}", {"data": {"type": "appStoreVersionLocalizations", "id": vlocs[loc]["id"], "attributes": attrs}})["data"]
        else:
            vl = a.call("POST", "/v1/appStoreVersionLocalizations", {"data": {"type": "appStoreVersionLocalizations", "attributes": {"locale": loc, **attrs},
                "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}}}})["data"]
        print("Store text", loc, "ok")
        if not o.no_media:
            media(a, vl["id"], folder, "screenshots", SHOT_TYPES, "appScreenshotSets", "screenshotDisplayType", "appScreenshots")
            media(a, vl["id"], folder, "previews", PREVIEW_TYPES, "appPreviewSets", "previewType", "appPreviews")

    # App Review contact (only if given as secrets) and notes
    rd = {"demoAccountRequired": False, "notes": read("default", "review_notes") or ""}
    for env, k in (("REVIEW_FIRST_NAME", "contactFirstName"), ("REVIEW_LAST_NAME", "contactLastName"), ("REVIEW_PHONE", "contactPhone"), ("REVIEW_EMAIL", "contactEmail")):
        if os.environ.get(env):
            rd[k] = os.environ[env]
    try:
        cur = a.call("GET", f"/v1/appStoreVersions/{vid}/appStoreReviewDetail", ok=(200, 404))
        if cur.get("data"):
            a.call("PATCH", f"/v1/appStoreReviewDetails/{cur['data']['id']}", {"data": {"type": "appStoreReviewDetails", "id": cur["data"]["id"], "attributes": rd}})
        else:
            a.call("POST", "/v1/appStoreReviewDetails", {"data": {"type": "appStoreReviewDetails", "attributes": rd,
                "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}}}})
        print("Review details ok" + ("" if "contactEmail" in rd else " (contact info missing: fill it in App Store Connect)"))
    except RuntimeError as e:
        print("WARN review details:", e)

    # in-app purchase "Escape completo": review screenshot (the paywall) and review note
    iap = None
    try:
        iaps = a.get(f"/v1/apps/{aid}/inAppPurchasesV2", **{"filter[productId]": IAP_ID})["data"]
        iap = iaps[0] if iaps else None
        if not iap:
            print("WARN in-app purchase", IAP_ID, "not found in App Store Connect")
        else:
            print("In-app purchase", IAP_ID, iap["attributes"].get("state"))
            a.call("PATCH", f"/v2/inAppPurchases/{iap['id']}", {"data": {"type": "inAppPurchases", "id": iap["id"], "attributes": {
                "reviewNote": "Non-consumable. Opens from the title screen (FULL ESCAPE) and from Settings. Unlocks Horde mode, the heroes Kai, Nyx and Brisa and all wardrobe looks. RESTORE PURCHASE is on the same screen."}}})
            try:
                if not a.call("GET", f"/v2/inAppPurchases/{iap['id']}/inAppPurchaseAvailability", ok=(200, 404)).get("data"):
                    tl = terrs or [t["id"] for t in a.all("/v1/territories", limit=200)]
                    a.call("POST", "/v1/inAppPurchaseAvailabilities", {"data": {"type": "inAppPurchaseAvailabilities",
                        "attributes": {"availableInNewTerritories": True}, "relationships": {
                            "inAppPurchase": {"data": {"type": "inAppPurchases", "id": iap["id"]}},
                            "availableTerritories": {"data": [{"type": "territories", "id": t} for t in tl]}}}})
                    print("In-app purchase availability: all territories")
            except RuntimeError as e:
                print("WARN in-app purchase availability:", str(e)[:400])
            shotf = os.path.join(ROOT, "iap", "review-screenshot.png")
            cur = a.call("GET", f"/v2/inAppPurchases/{iap['id']}/appStoreReviewScreenshot")
            data = open(shotf, "rb").read()
            have = cur and cur.get("data")
            if have and have["attributes"].get("sourceFileChecksum") == hashlib.md5(data).hexdigest():
                raise _SameShot()  # same file already there: re-uploading it would leave the purchase "processing" at submit time
            if have:
                a.call("DELETE", f"/v1/inAppPurchaseAppStoreReviewScreenshots/{have['id']}")
            obj = a.call("POST", "/v1/inAppPurchaseAppStoreReviewScreenshots", {"data": {"type": "inAppPurchaseAppStoreReviewScreenshots",
                "attributes": {"fileName": "review-screenshot.png", "fileSize": len(data)},
                "relationships": {"inAppPurchaseV2": {"data": {"type": "inAppPurchases", "id": iap["id"]}}}}})["data"]
            for op in obj["attributes"]["uploadOperations"]:
                h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
                r = requests.request(op["method"], op["url"], headers=h, data=data[op["offset"]: op["offset"] + op["length"]], timeout=300)
                if r.status_code >= 300:
                    raise RuntimeError(f"upload part failed {r.status_code} {r.text[:300]}")
            a.call("PATCH", f"/v1/inAppPurchaseAppStoreReviewScreenshots/{obj['id']}", {"data": {"type": "inAppPurchaseAppStoreReviewScreenshots",
                "id": obj["id"], "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
            print("In-app purchase review screenshot uploaded")
    except _SameShot:
        print("In-app purchase review screenshot unchanged")
    except RuntimeError as e:
        print("WARN in-app purchase:", str(e)[:600])

    # Game Center achievement images (8-bit medals in store/ios/gamecenter/<id>.png), only where missing
    try:
        gcd = a.call("GET", f"/v1/apps/{aid}/gameCenterDetail", ok=(200, 404)).get("data")
        if gcd:
            done = 0
            for ach in a.all(f"/v1/gameCenterDetails/{gcd['id']}/gameCenterAchievements", limit=200):
                vid_ = (ach["attributes"].get("vendorIdentifier") or "").removeprefix("omf_")
                imgf = os.path.join(ROOT, "gamecenter", vid_ + ".png")
                if not os.path.exists(imgf):
                    continue
                data = open(imgf, "rb").read()
                for loc in a.all(f"/v1/gameCenterAchievements/{ach['id']}/localizations", limit=50):
                    if a.call("GET", f"/v1/gameCenterAchievementLocalizations/{loc['id']}/gameCenterAchievementImage", ok=(200, 404)).get("data"):
                        continue
                    obj = a.call("POST", "/v1/gameCenterAchievementImages", {"data": {"type": "gameCenterAchievementImages",
                        "attributes": {"fileName": vid_ + ".png", "fileSize": len(data)},
                        "relationships": {"gameCenterAchievementLocalization": {"data": {"type": "gameCenterAchievementLocalizations", "id": loc["id"]}}}}})["data"]
                    for op in obj["attributes"]["uploadOperations"]:
                        h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
                        r = requests.request(op["method"], op["url"], headers=h, data=data[op["offset"]: op["offset"] + op["length"]], timeout=300)
                        if r.status_code >= 300:
                            raise RuntimeError(f"upload part failed {r.status_code} {r.text[:300]}")
                    a.call("PATCH", f"/v1/gameCenterAchievementImages/{obj['id']}", {"data": {"type": "gameCenterAchievementImages", "id": obj["id"], "attributes": {"uploaded": True}}})
                    done += 1
            print("Game Center achievement images uploaded:", done)
    except RuntimeError as e:
        print("WARN Game Center images:", str(e)[:400])

    # newest valid build with this version
    builds = [] if o.build == "skip" else a.get("/v1/builds", **{"filter[app]": aid, "filter[preReleaseVersion.version]": o.version,
                                    "filter[processingState]": "VALID", "sort": "-uploadedDate", "limit": 1,
                                    **({"filter[version]": o.build} if o.build else {})})["data"]
    if builds:
        b = builds[0]
        a.call("PATCH", f"/v1/appStoreVersions/{vid}/relationships/build", {"data": {"type": "builds", "id": b["id"]}})
        print("Build attached:", o.version, "build", b["attributes"]["version"])
    else:
        print(f"WARN no processed build with version {o.version} yet: run TestFlight (Escape) with version {o.version} first")

    # Game Center: every achievement and leaderboard goes live with this version (a release waits for the approval)
    try:
        gcd = a.call("GET", f"/v1/apps/{aid}/gameCenterDetail", ok=(200, 404)).get("data")
        if gcd:
            try:
                if not a.call("GET", f"/v1/appStoreVersions/{vid}/gameCenterAppVersion", ok=(200, 404)).get("data"):
                    a.call("POST", "/v1/gameCenterAppVersions", {"data": {"type": "gameCenterAppVersions",
                        "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}}}})
                    print("Game Center enabled on version", o.version)
            except RuntimeError as e:
                print("WARN Game Center on version:", str(e)[:300])
            for kind, rel, rtype, field in (("gameCenterAchievements", "achievementReleases", "gameCenterAchievementReleases", "gameCenterAchievement"),
                                            ("gameCenterLeaderboards", "leaderboardReleases", "gameCenterLeaderboardReleases", "gameCenterLeaderboard")):
                items = a.all(f"/v1/gameCenterDetails/{gcd['id']}/{kind}", limit=200)
                done = {r["relationships"][field]["data"]["id"] for r in a.all(f"/v1/gameCenterDetails/{gcd['id']}/{rel}", limit=200, include=field)
                        if r.get("relationships", {}).get(field, {}).get("data")}
                n, bad = 0, []
                for it in items:
                    if it["id"] in done or it["attributes"].get("archived"):
                        continue
                    try:
                        a.call("POST", f"/v1/{rtype}", {"data": {"type": rtype, "relationships": {
                            "gameCenterDetail": {"data": {"type": "gameCenterDetails", "id": gcd["id"]}},
                            field: {"data": {"type": kind, "id": it["id"]}}}}})
                        n += 1
                    except RuntimeError as e:
                        bad.append(it["attributes"].get("vendorIdentifier", it["id"]) + ": " + str(e)[:200])
                print(f"Game Center {kind}: {len(items)} total, {len(done)} already released, {n} added to this version")
                for b_ in bad:
                    print("  WARN", b_)
    except RuntimeError as e:
        print("WARN Game Center releases:", str(e)[:400])

    if o.submit:
        if not builds:
            sys.exit("Not submitting: no build attached")
        if iap and iap["attributes"].get("state") in ("READY_TO_SUBMIT", "MISSING_METADATA", "DEVELOPER_ACTION_NEEDED", "REJECTED"):
            try:
                a.call("POST", "/v1/inAppPurchaseSubmissions", {"data": {"type": "inAppPurchaseSubmissions",
                    "relationships": {"inAppPurchaseV2": {"data": {"type": "inAppPurchases", "id": iap["id"]}}}}})
                print("In-app purchase added to the review")
            except RuntimeError as e:
                print("WARN in-app purchase submission (add it on the version page in App Store Connect):", str(e)[:2500])
        # reuse a draft submission left by an earlier failed run instead of opening a second one
        drafts = a.get("/v1/reviewSubmissions", **{"filter[app]": aid, "filter[platform]": "IOS",
                                                    "filter[state]": "READY_FOR_REVIEW,UNRESOLVED_ISSUES"})["data"]
        sub = drafts[0] if drafts else a.call("POST", "/v1/reviewSubmissions", {"data": {"type": "reviewSubmissions", "attributes": {"platform": "IOS"},
            "relationships": {"app": {"data": {"type": "apps", "id": aid}}}}})["data"]
        try:
            a.call("POST", "/v1/reviewSubmissionItems", {"data": {"type": "reviewSubmissionItems", "relationships": {
                "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": sub["id"]}},
                "appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}}}})
        except RuntimeError as e:
            if not drafts:
                raise
            print("Version already in the draft submission:", str(e)[:200])
        a.call("PATCH", f"/v1/reviewSubmissions/{sub['id']}", {"data": {"type": "reviewSubmissions", "id": sub["id"], "attributes": {"submitted": True}}})
        print("SUBMITTED for App Review")
    else:
        print("Done. Not submitted (run with submit = true when the user says so).")


if __name__ == "__main__":
    main()
