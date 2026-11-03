#!/usr/bin/env python3
"""Prepara com.onemorefloor.escape en Apple: capacidades del App ID (Game Center, iCloud),
dispositivo de relleno opcional, y Game Center (marcadores + logros) en App Store Connect.
Idempotente: solo crea lo que falta. Variables: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH, BUNDLE_ID,
REGISTER_PLACEHOLDER_DEVICE=1 (opcional), GC_DATA (ruta a native/gamecenter.json)."""
import json, os, sys, time, uuid, datetime
import jwt, requests

API = "https://api.appstoreconnect.apple.com"
KEY_ID, ISSUER = os.environ["ASC_KEY_ID"], os.environ["ASC_ISSUER_ID"]
KEY = open(os.path.expanduser(os.environ.get("ASC_KEY_PATH", "~/keys/AuthKey.p8"))).read()
BUNDLE_ID = os.environ.get("BUNDLE_ID", "com.onemorefloor.escape")
problems = []

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
        d = call("GET", url)
        out += d.get("data", [])
        nxt = d.get("links", {}).get("next")
        url = nxt.replace(API, "") if nxt else None
    return out

def step(name, fn):
    try:
        fn()
    except Exception as e:
        print(f"!! {name}: {e}")
        problems.append(name)

# ---------- App ID y capacidades ----------
bundle = call("GET", f"/v1/bundleIds?filter[identifier]={BUNDLE_ID}&include=bundleIdCapabilities")
bundle_rec = next((b for b in bundle["data"] if b["attributes"]["identifier"] == BUNDLE_ID), None)
if not bundle_rec:
    sys.exit(f"No existe el App ID {BUNDLE_ID}")
caps = {c["attributes"]["capabilityType"] for c in bundle.get("included", []) if c["type"] == "bundleIdCapabilities"}
print("Capacidades actuales:", sorted(caps))

def enable(cap, settings=None):
    if cap in caps:
        return
    body = {"data": {"type": "bundleIdCapabilities", "attributes": {"capabilityType": cap},
                     "relationships": {"bundleId": {"data": {"type": "bundleIds", "id": bundle_rec["id"]}}}}}
    if settings:
        body["data"]["attributes"]["settings"] = settings
    call("POST", "/v1/bundleIdCapabilities", body)
    print("Activada capacidad", cap)

step("capacidad GAME_CENTER", lambda: enable("GAME_CENTER"))
step("capacidad ICLOUD", lambda: enable("ICLOUD", [{"key": "ICLOUD_VERSION", "options": [{"key": "XCODE_6"}]}]))

# ---------- Dispositivo (la firma automática necesita al menos uno) ----------
def devices():
    ds = [d for d in all_pages("/v1/devices?limit=200") if d["attributes"]["status"] == "ENABLED"
          and d["attributes"]["platform"] in ("IOS", "UNIVERSAL")]
    print("Dispositivos iOS registrados:", len(ds))
    if not ds and os.environ.get("REGISTER_PLACEHOLDER_DEVICE") == "1":
        udid = uuid.uuid4().hex + uuid.uuid4().hex[:8]  # 40 hex, formato UDID clásico
        call("POST", "/v1/devices", {"data": {"type": "devices", "attributes":
             {"name": "CI (relleno)", "platform": "IOS", "udid": udid}}})
        print("Registrado dispositivo de relleno")
    elif not ds:
        raise RuntimeError("No hay dispositivos iOS registrados: registra tu iPhone en developer.apple.com")
step("dispositivos", devices)

# ---------- Game Center ----------
def game_center():
    data = json.load(open(os.environ.get("GC_DATA", "native/gamecenter.json")))
    pre = data["prefix"]
    apps = call("GET", f"/v1/apps?filter[bundleId]={BUNDLE_ID}")["data"]
    if not apps:
        raise RuntimeError("No hay app en App Store Connect con ese Bundle ID")
    app_id = apps[0]["id"]
    det = call("GET", f"/v1/apps/{app_id}/gameCenterDetail", ok_missing=True)
    det_id = det["data"]["id"] if det and det.get("data") else None
    if not det_id:
        det_id = call("POST", "/v1/gameCenterDetails", {"data": {"type": "gameCenterDetails",
                      "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}})["data"]["id"]
        print("Creado detalle de Game Center")
    rel = {"gameCenterDetail": {"data": {"type": "gameCenterDetails", "id": det_id}}}
    locales = [("en-US", "en"), ("es-ES", "es"), ("es-MX", "es")]

    have_lb = {l["attributes"]["vendorIdentifier"]: l["id"]
               for l in all_pages(f"/v1/gameCenterDetails/{det_id}/gameCenterLeaderboards?limit=200")}
    for lb in data["leaderboards"]:
        vid = pre + lb["id"]
        if vid in have_lb:
            continue
        attrs = {"referenceName": lb["en"], "vendorIdentifier": vid, "defaultFormatter": lb["formatter"],
                 "submissionType": "BEST_SCORE", "scoreSortType": "DESC"}
        try:
            if lb.get("daily"):
                start = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
                d_attrs = dict(attrs, recurrenceStartDate=start, recurrenceDuration="P1D", recurrenceRule="FREQ=DAILY;INTERVAL=1")
                try:
                    new = call("POST", "/v1/gameCenterLeaderboards", {"data": {"type": "gameCenterLeaderboards", "attributes": d_attrs, "relationships": rel}})
                except Exception as e:
                    print("  Recurrente no aceptado, creo clásico:", str(e)[:200])
                    new = call("POST", "/v1/gameCenterLeaderboards", {"data": {"type": "gameCenterLeaderboards", "attributes": attrs, "relationships": rel}})
            else:
                new = call("POST", "/v1/gameCenterLeaderboards", {"data": {"type": "gameCenterLeaderboards", "attributes": attrs, "relationships": rel}})
            lid = new["data"]["id"]
            for loc, lang in locales:
                la = {"locale": loc, "name": lb[lang]}
                if lb.get("suffix_" + lang):
                    la["formatterSuffix"] = lb["suffix_" + lang]
                    la["formatterSuffixSingular"] = lb["suffix_" + lang]
                call("POST", "/v1/gameCenterLeaderboardLocalizations", {"data": {"type": "gameCenterLeaderboardLocalizations",
                     "attributes": la, "relationships": {"gameCenterLeaderboard": {"data": {"type": "gameCenterLeaderboards", "id": lid}}}}})
            print("Creado marcador", vid)
        except Exception as e:
            print("!! marcador", vid, e); problems.append("marcador " + vid)

    have_ach = {a["attributes"]["vendorIdentifier"]
                for a in all_pages(f"/v1/gameCenterDetails/{det_id}/gameCenterAchievements?limit=200")}
    created = 0
    for a in data["achievements"]:
        vid = pre + a["id"]
        if vid in have_ach:
            continue
        try:
            new = call("POST", "/v1/gameCenterAchievements", {"data": {"type": "gameCenterAchievements", "attributes": {
                "referenceName": a["en"], "vendorIdentifier": vid, "points": a["points"],
                "showBeforeEarned": not a["hidden"], "repeatable": False}, "relationships": rel}})
            aid = new["data"]["id"]
            for loc, lang in locales:
                name, cond = a[lang], a["cond_" + lang]
                call("POST", "/v1/gameCenterAchievementLocalizations", {"data": {"type": "gameCenterAchievementLocalizations",
                     "attributes": {"locale": loc, "name": name[:30], "beforeEarnedDescription": cond[:200], "afterEarnedDescription": cond[:200]},
                     "relationships": {"gameCenterAchievement": {"data": {"type": "gameCenterAchievements", "id": aid}}}}})
            created += 1
        except Exception as e:
            print("!! logro", vid, e); problems.append("logro " + vid)
    print(f"Logros: {len(have_ach)} existían, {created} creados")

step("Game Center", game_center)

if problems:
    print("Terminado con avisos:", ", ".join(problems))
    if "dispositivos" in problems:
        sys.exit(2)   # sin dispositivo la firma fallará; mejor parar aquí con un mensaje claro
else:
    print("Apple listo: capacidades y Game Center al día")
