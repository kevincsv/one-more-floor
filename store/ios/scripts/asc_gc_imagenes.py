#!/usr/bin/env python3
"""Imágenes de los logros de Game Center (512x512, pixel art) en App Store Connect.
Apple no deja publicar un logro sin imagen, y sin logros publicados Game Center muestra 0/0 en la App Store.
Por defecto SOLO MIRA: lista qué logros (por idioma) no tienen imagen. Con SUBIR=1 sube las que faltan
desde ios-app/gamecenter-imagenes/omf_<id>.png. No toca nada más.
Variables: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH, BUNDLE_ID, IMG_DIR, SUBIR=1 (opcional)."""
import os, sys, time
import jwt, requests

API = "https://api.appstoreconnect.apple.com"
KEY_ID, ISSUER = os.environ["ASC_KEY_ID"], os.environ["ASC_ISSUER_ID"]
KEY = open(os.path.expanduser(os.environ.get("ASC_KEY_PATH", "~/keys/AuthKey.p8"))).read()
BUNDLE_ID = os.environ.get("BUNDLE_ID", "com.onemorefloor.escape")
IMG_DIR = os.environ.get("IMG_DIR", os.path.join(os.path.dirname(__file__), "..", "gamecenter-imagenes"))
SUBIR = os.environ.get("SUBIR") == "1"

def token():
    now = int(time.time())
    return jwt.encode({"iss": ISSUER, "iat": now, "exp": now + 1100, "aud": "appstoreconnect-v1"},
                      KEY, algorithm="ES256", headers={"kid": KEY_ID, "typ": "JWT"})

def call(method, path, body=None, ok_missing=False):
    r = requests.request(method, API + path, json=body, timeout=60,
                         headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    if ok_missing and r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:600]}")
    return r.json() if r.text else {}

def all_pages(path):
    out, url = [], path
    while url:
        d = call("GET", url); out += d.get("data", [])
        nxt = d.get("links", {}).get("next"); url = nxt.replace(API, "") if nxt else None
    return out

app_id = call("GET", f"/v1/apps?filter[bundleId]={BUNDLE_ID}")["data"][0]["id"]
det_id = call("GET", f"/v1/apps/{app_id}/gameCenterDetail")["data"]["id"]
achs = all_pages(f"/v1/gameCenterDetails/{det_id}/gameCenterAchievements?limit=200")
print(f"Logros en App Store Connect: {len(achs)}")
falta, subidas, problemas = 0, 0, []
for a in achs:
    vid = a["attributes"]["vendorIdentifier"]
    img = os.path.join(IMG_DIR, vid + ".png")
    for loc in all_pages(f"/v1/gameCenterAchievements/{a['id']}/localizations?limit=50"):
        have = call("GET", f"/v1/gameCenterAchievementLocalizations/{loc['id']}/gameCenterAchievementImage", ok_missing=True)
        if have and have.get("data"):
            continue
        falta += 1
        print(f"  sin imagen: {vid} ({loc['attributes']['locale']})")
        if not SUBIR:
            continue
        if not os.path.exists(img):
            problemas.append(f"{vid}: no existe {img}"); continue
        try:
            data = open(img, "rb").read()
            r = call("POST", "/v1/gameCenterAchievementImages", {"data": {"type": "gameCenterAchievementImages",
                     "attributes": {"fileName": vid + ".png", "fileSize": len(data)},
                     "relationships": {"gameCenterAchievementLocalization": {"data": {"type": "gameCenterAchievementLocalizations", "id": loc["id"]}}}}})
            iid = r["data"]["id"]
            for op in r["data"]["attributes"].get("uploadOperations") or []:
                part = data[op["offset"]:op["offset"] + op["length"]]
                h = {x["name"]: x["value"] for x in op.get("requestHeaders") or []}
                requests.request(op["method"], op["url"], data=part, headers=h, timeout=120).raise_for_status()
            call("PATCH", f"/v1/gameCenterAchievementImages/{iid}", {"data": {"type": "gameCenterAchievementImages", "id": iid, "attributes": {"uploaded": True}}})
            subidas += 1
        except Exception as e:
            problemas.append(f"{vid} {loc['attributes']['locale']}: {str(e)[:300]}")
print(f"Sin imagen: {falta} · subidas ahora: {subidas}")
for p in problemas: print("!!", p)
sys.exit(1 if problemas else 0)
