#!/usr/bin/env python3
"""Lista las últimas builds de la app en App Store Connect con su estado de procesado (solo lectura)."""
import os, time, jwt, requests
API = "https://api.appstoreconnect.apple.com"
KEY = open(os.path.expanduser(os.environ.get("ASC_KEY_PATH", "~/keys/AuthKey.p8"))).read()
def tok():
    n = int(time.time())
    return jwt.encode({"iss": os.environ["ASC_ISSUER_ID"], "iat": n, "exp": n + 1100, "aud": "appstoreconnect-v1"},
                      KEY, algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"})
def get(p):
    r = requests.get(API + p, headers={"Authorization": "Bearer " + tok()}, timeout=60); r.raise_for_status(); return r.json()
app = get("/v1/apps?filter[bundleId]=" + os.environ.get("BUNDLE_ID", "com.onemorefloor.escape"))["data"][0]["id"]
d = get(f"/v1/builds?filter[app]={app}&sort=-uploadedDate&limit=8&include=preReleaseVersion")
vers = {i["id"]: i["attributes"]["version"] for i in d.get("included", []) if i["type"] == "preReleaseVersions"}
for b in d["data"]:
    a = b["attributes"]; pv = b["relationships"]["preReleaseVersion"]["data"]
    print(f'{vers.get(pv["id"] if pv else "", "?")} ({a["version"]}) {a["processingState"]} uploaded={a["uploadedDate"]} expired={a.get("expired")}')
