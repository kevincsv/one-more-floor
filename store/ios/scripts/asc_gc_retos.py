#!/usr/bin/env python3
"""Game Center activities and challenges (iOS 26 Games app) for One More Floor Escape.

Creates or fixes, idempotently:
  - 5 activities (climb_normal, climb_hard, climb_easy, daily, daily_hard), each linked to its leaderboard,
    with en-US / es-ES / es-MX texts and a 3840x2160 default image (store/ios/gc-retos/<id>-3840x2160.png).
  - the challenges named in RETOS (comma list of C1,C2,C3,...), each on its leaderboard.
It never creates releases and never submits: they go out with an app version only when the user says so.
RETOS=probe tries a throwaway challenge on the recurring daily board, reports whether Apple accepts it, then deletes it.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import requests
from asc_publish import ASC, BUNDLE_ID

IMG = os.path.join(os.path.dirname(__file__), "..", "gc-retos")
LOCS = ("en-US", "es-ES", "es-MX")
ACTS = {
    "climb_normal": ("omf_height", "Climb (Normal)", "Escalar (Normal)",
                     "The endless climb on Normal. How high can you get?", "La subida sin fin en Normal. ¿Hasta dónde llegas?"),
    "climb_hard": ("omf_height_hard", "Climb (Hardcore)", "Escalar (Hardcore)",
                   "The endless climb on Hardcore: solid platforms, faster camera.", "La subida sin fin en Hardcore: plataformas sólidas y cámara más rápida."),
    "climb_easy": ("omf_height_easy", "Climb (Easy)", "Escalar (Fácil)",
                   "The endless climb on Easy, a relaxed way to play.", "La subida sin fin en Fácil, para jugar tranquilo."),
    "daily": ("omf_daily", "Daily Challenge", "Reto diario",
              "Today's tower, the same for everyone. Resets at 00:00 UTC.", "La torre de hoy, igual para todos. Se reinicia a las 00:00 UTC."),
    "daily_hard": ("omf_daily_hard", "Daily Challenge Hardcore", "Reto diario Hardcore",
                   "Today's tower on Hardcore, the same for everyone.", "La torre de hoy en Hardcore, igual para todos."),
}
CHALS = {  # code: (challenge id, leaderboard, image, EN name, ES name, EN text, ES text)
    "C1": ("omf_ch_height", "omf_height", "climb_normal", "Who climbs higher?", "¿Quién sube más?",
           "Climb on Normal and beat your friends' height.", "Sube en Normal y supera la altura de tus amigos."),
    "C2": ("omf_ch_height_hard", "omf_height_hard", "climb_hard", "Hardcore: who climbs higher?", "Hardcore: ¿quién sube más?",
           "Climb on Hardcore and beat your friends' height.", "Sube en Hardcore y supera la altura de tus amigos."),
    "C3": ("omf_ch_height_easy", "omf_height_easy", "climb_easy", "Easy climb", "Subida tranquila",
           "A relaxed climb on Easy. Highest wins.", "Una subida tranquila en Fácil. Gana quien llegue más alto."),
    "C4": ("omf_ch_daily", "omf_daily", "daily", "Today's tower", "La torre de hoy",
           "Same tower for everyone today. Highest wins.", "La misma torre para todos hoy. Gana quien llegue más alto."),
    "C5": ("omf_ch_daily_hard", "omf_daily_hard", "daily_hard", "Today's tower: Hardcore", "La torre de hoy: Hardcore",
           "Today's tower on Hardcore. Highest wins.", "La torre de hoy en Hardcore. Gana quien llegue más alto."),
}

a = ASC()
aid = a.get("/v1/apps", **{"filter[bundleId]": BUNDLE_ID})["data"][0]["id"]
gcd = a.call("GET", f"/v1/apps/{aid}/gameCenterDetail")["data"]["id"]
lbs = {l["attributes"]["vendorIdentifier"]: l for l in a.all(f"/v1/gameCenterDetails/{gcd}/gameCenterLeaderboards", limit=200)}
for k, l in lbs.items():
    at = l["attributes"]
    print("LEADERBOARD", k, "recurring:", bool(at.get("recurrenceRule") or at.get("recurrenceDuration")), at.get("recurrenceDuration") or "")

def texts(en, es, den, des):
    return {"en-US": (en, den), "es-ES": (es, des), "es-MX": (es, des)}

def upload_image(kind, rel, rel_type, rel_id, path):
    data = open(path, "rb").read()
    obj = a.call("POST", f"/v1/{kind}", {"data": {"type": kind, "attributes": {"fileName": os.path.basename(path), "fileSize": len(data)},
                 "relationships": {rel: {"data": {"type": rel_type, "id": rel_id}}}}})["data"]
    for op in obj["attributes"]["uploadOperations"]:
        h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
        r = requests.request(op["method"], op["url"], headers=h, data=data[op["offset"]: op["offset"] + op["length"]], timeout=300)
        if r.status_code >= 300:
            raise RuntimeError(f"upload part failed {r.status_code} {r.text[:300]}")
    a.call("PATCH", f"/v1/{kind}/{obj['id']}", {"data": {"type": kind, "id": obj["id"], "attributes": {"uploaded": True}}})

def fill_version(base, vtype, ltype, itype, owner_rel, owner_type, owner_id, tx, img):
    """Newest editable version of an activity/challenge, with localizations and default image."""
    vers = a.all(f"/v1/{owner_type}/{owner_id}/versions")
    v = next((x for x in vers if x["attributes"].get("state") in ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", None)), None)
    if not v:
        if vers:
            print("  version state:", [x["attributes"].get("state") for x in vers], "(not editable, left as is)"); return
        v = a.call("POST", f"/v1/{vtype}", {"data": {"type": vtype, "relationships": {owner_rel: {"data": {"type": owner_type, "id": owner_id}}}}})["data"]
        print("  version created")
    have = {l["attributes"]["locale"]: l for l in a.all(f"/v1/{vtype}/{v['id']}/localizations")}
    for loc, (name, desc) in tx.items():
        if loc in have:
            l = have[loc]
            if l["attributes"].get("name") != name or l["attributes"].get("description") != desc:
                a.call("PATCH", f"/v1/{ltype}/{l['id']}", {"data": {"type": ltype, "id": l["id"], "attributes": {"name": name, "description": desc}}})
        else:
            a.call("POST", f"/v1/{ltype}", {"data": {"type": ltype, "attributes": {"locale": loc, "name": name, "description": desc},
                   "relationships": {"version": {"data": {"type": vtype, "id": v["id"]}}}}})
    print("  texts ok:", ", ".join(tx))
    if a.call("GET", f"/v1/{vtype}/{v['id']}/defaultImage", ok=(200, 404)).get("data"):
        print("  image already there")
    else:
        upload_image(itype, "version", vtype, v["id"], os.path.join(IMG, img + "-3840x2160.png")); print("  image uploaded")

# activities
acts = {x["attributes"]["vendorIdentifier"]: x for x in a.all(f"/v1/gameCenterDetails/{gcd}/gameCenterActivities", limit=50)}
for aid_, (lb, en, es, den, des) in ACTS.items():
    try:
        act = acts.get(aid_)
        if not act:
            act = a.call("POST", "/v1/gameCenterActivities", {"data": {"type": "gameCenterActivities",
                  "attributes": {"referenceName": en, "vendorIdentifier": aid_, "playStyle": "ASYNCHRONOUS", "supportsPartyCode": False},
                  "relationships": {"gameCenterDetail": {"data": {"type": "gameCenterDetails", "id": gcd}}}}})["data"]
            print("ACTIVITY", aid_, "created")
        else:
            print("ACTIVITY", aid_, "exists")
        if lb in lbs:
            try:
                a.call("POST", f"/v1/gameCenterActivities/{act['id']}/relationships/leaderboardsV2", {"data": [{"type": "gameCenterLeaderboards", "id": lbs[lb]["id"]}]})
                print("  linked to", lb)
            except RuntimeError as e:
                print("  WARN link", lb, str(e)[:300])
        fill_version("act", "gameCenterActivityVersions", "gameCenterActivityLocalizations", "gameCenterActivityImages",
                     "activity", "gameCenterActivities", act["id"], texts(en, es, den, des), aid_)
    except RuntimeError as e:
        print("WARN activity", aid_, str(e)[:900])

# challenges
want = [c.strip().upper() for c in os.environ.get("RETOS", "").split(",") if c.strip()]
chals = {x["attributes"]["vendorIdentifier"]: x for x in a.all(f"/v1/gameCenterDetails/{gcd}/gameCenterChallenges", limit=50)}
if "PROBE" in want:
    try:
        t = a.call("POST", "/v1/gameCenterChallenges", {"data": {"type": "gameCenterChallenges",
            "attributes": {"referenceName": "probe daily", "vendorIdentifier": "omf_probe_daily_tmp", "challengeType": "LEADERBOARD", "repeatable": True},
            "relationships": {"gameCenterDetail": {"data": {"type": "gameCenterDetails", "id": gcd}},
                              "leaderboardV2": {"data": {"type": "gameCenterLeaderboards", "id": lbs["omf_daily"]["id"]}}}}})["data"]
        print("PROBE: Apple ACCEPTS a challenge on the recurring daily board")
        a.call("DELETE", f"/v1/gameCenterChallenges/{t['id']}"); print("PROBE: test challenge deleted")
    except RuntimeError as e:
        print("PROBE: Apple REJECTS a challenge on the recurring daily board:", str(e)[:700])
for code in want:
    if code not in CHALS: continue
    cid, lb, img, en, es, den, des = CHALS[code]
    try:
        ch = chals.get(cid)
        if not ch:
            ch = a.call("POST", "/v1/gameCenterChallenges", {"data": {"type": "gameCenterChallenges",
                 "attributes": {"referenceName": en, "vendorIdentifier": cid, "challengeType": "LEADERBOARD", "repeatable": True},
                 "relationships": {"gameCenterDetail": {"data": {"type": "gameCenterDetails", "id": gcd}},
                                   "leaderboardV2": {"data": {"type": "gameCenterLeaderboards", "id": lbs[lb]["id"]}}}}})["data"]
            print("CHALLENGE", code, cid, "created on", lb)
        else:
            print("CHALLENGE", code, cid, "exists")
        fill_version("ch", "gameCenterChallengeVersions", "gameCenterChallengeLocalizations", "gameCenterChallengeImages",
                     "challenge", "gameCenterChallenges", ch["id"], texts(en, es, den, des), img)
    except RuntimeError as e:
        print("WARN challenge", code, str(e)[:900])
print("Done. Nothing released or submitted.")
