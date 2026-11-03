#!/usr/bin/env python3
"""Lista los certificados del equipo y, con --revoke, revoca los de desarrollo que crea Xcode en CI
("Created via API"). Cada ejecución de CI firma con un llavero nuevo y Xcode crea un certificado de
desarrollo; sin limpieza se llega al máximo de Apple. Aprobado por Kevin el 2026-11-03."""
import os, sys, time, jwt, requests
API = "https://api.appstoreconnect.apple.com"
KEY = open(os.path.expanduser(os.environ.get("ASC_KEY_PATH", "~/keys/AuthKey.p8"))).read()
def tok():
    n = int(time.time())
    return jwt.encode({"iss": os.environ["ASC_ISSUER_ID"], "iat": n, "exp": n + 1100, "aud": "appstoreconnect-v1"},
                      KEY, algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"})
def req(m, p):
    r = requests.request(m, API + p, headers={"Authorization": "Bearer " + tok()}, timeout=60)
    if r.status_code >= 400: raise RuntimeError(f"{m} {p} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}
certs = req("GET", "/v1/certificates?limit=200")["data"]
dev = [c for c in certs if c["attributes"]["certificateType"] in ("DEVELOPMENT", "IOS_DEVELOPMENT")]
print(f"Certificados: {len(certs)} en total, {len(dev)} de desarrollo")
for c in certs:
    a = c["attributes"]
    print(f"  {a['certificateType']:<22} {a.get('name','')!r:<45} {a.get('displayName','')!r} caduca {(a.get('expirationDate') or '')[:10]}")
if "--revoke" in sys.argv:
    ci = [c for c in dev if "Created via API" in (c["attributes"].get("name", "") + " " + c["attributes"].get("displayName", ""))]
    for c in ci:
        req("DELETE", f"/v1/certificates/{c['id']}")
    print(f"Revocados {len(ci)} certificados de desarrollo creados por CI")
