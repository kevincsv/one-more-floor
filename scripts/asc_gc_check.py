#!/usr/bin/env python3
"""Solo lectura: estado de los marcadores de Game Center y si están en la versión de la app."""
import os, time, json, jwt, requests
API = "https://api.appstoreconnect.apple.com"
KEY = open(os.path.expanduser(os.environ.get("ASC_KEY_PATH", "~/keys/AuthKey.p8"))).read()
def tok():
    n = int(time.time())
    return jwt.encode({"iss": os.environ["ASC_ISSUER_ID"], "iat": n, "exp": n + 1100, "aud": "appstoreconnect-v1"},
                      KEY, algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"})
def get(p, ok404=False):
    r = requests.get(API + p, headers={"Authorization": "Bearer " + tok()}, timeout=60)
    if ok404 and r.status_code in (404, 403): return {"_status": r.status_code, "_text": r.text[:300]}
    r.raise_for_status(); return r.json()
app = get("/v1/apps?filter[bundleId]=com.onemorefloor.escape")["data"][0]["id"]
det = get(f"/v1/apps/{app}/gameCenterDetail", ok404=True)
print("gameCenterDetail:", json.dumps(det.get("data", det), indent=0)[:800])
did = det["data"]["id"]
for lb in get(f"/v1/gameCenterDetails/{did}/gameCenterLeaderboards?limit=50")["data"]:
    print("LB", json.dumps(lb["attributes"]))
for rel in ("gameCenterAppVersions",):
    print(rel, json.dumps(get(f"/v1/gameCenterDetails/{did}/{rel}?limit=10", ok404=True))[:1500])
rel = get(f"/v1/gameCenterDetails/{did}/leaderboardReleases?limit=50", ok404=True)
print("leaderboardReleases:", json.dumps(rel)[:2000])
