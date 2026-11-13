// One More Floor Escape · duel relay for Cloudflare (Worker + one Durable Object).
// Same protocol as ../relay/server.js, so the game only needs the wss:// URL:
//   {t:"create"} -> {t:"room",code,role:"host"} · {t:"join",code} -> {t:"joined",code,role:"guest"} | {t:"err",e:"nosuch"|"full"|"busy"}
//   {t:"queue",diff} -> both get {t:"matched",code,role} · {t:"leave"} · {t:"msg",d} -> the other player gets {t:"msg",d}
//   {t:"peer",on:true|false} when the other player arrives or leaves.
// It only forwards messages. No accounts, no storage, nothing logged, no IPs kept.
// One Durable Object ("hub") holds every connection, like the single Node process does.
// It uses WebSocket hibernation, so an idle relay costs nothing; each socket keeps its own
// room and role in its attachment, and the room map is rebuilt from them after a wake-up.

const CH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789", MAX_MSG = 2048;

// v2 (2026-11-11): STUDIO NEWS. GET /news -> the contents of noticias.json, shared by every Iron Sprite game.
// To change the news: edit noticias.json (newest item first, give it a new "id") and run npx wrangler deploy.
import NEWS from "./noticias.json";
// media for the news (small files bundled into the Worker, served with Range support so iPhone video plays)
import FM_CLIP from "./media/fm-clip.mp4";
import FM_POSTER from "./media/fm-clip-poster.webp";
const MEDIA = { "/news/fm-clip.mp4": [FM_CLIP, "video/mp4"], "/news/fm-clip-poster.webp": [FM_POSTER, "image/webp"] };
function serveMedia(req, m) { const buf = new Uint8Array(m[0]), n = buf.length, h = { "content-type": m[1], "accept-ranges": "bytes", "cache-control": "public, max-age=86400", "access-control-allow-origin": "*" };
  const r = /bytes=(\d*)-(\d*)/.exec(req.headers.get("range") || "");
  if (r) { let a = r[1] === "" ? n - +r[2] : +r[1], b = r[1] !== "" && r[2] !== "" ? +r[2] : n - 1; a = Math.max(0, a); b = Math.min(n - 1, b);
    if (a > b) return new Response(null, { status: 416, headers: { ...h, "content-range": `bytes */${n}` } });
    return new Response(buf.slice(a, b + 1), { status: 206, headers: { ...h, "content-range": `bytes ${a}-${b}/${n}`, "content-length": String(b - a + 1) } }); }
  return new Response(buf, { headers: { ...h, "content-length": String(n) } }); }
// v2 (2026-11-11): single-use REDEEM CODES. POST /redeem {"code":"XXXXX-XXXXX"} -> {ok:true,reward} | {e:"bad"|"used"|"off"}.
// The Worker checks the code with the same maths as the game (secret in the REDEEM_SECRET Worker secret, never in files),
// then one "codes" Durable Object marks it used atomically. Stored: only the code and the day it was used. No IPs, no ids.
const RD_T = 268435456, RD_P = 4194304, RD_REWARDS = [1, 2, 3, 4];
const rdH = (sec, n, salt) => { let h = 0x811c9dc5 ^ salt; const s = sec + ":" + n + ":" + salt;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b); h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35); h ^= h >>> 16; return h >>> 0; };
function rdDecode(sec, txt) { const s = String(txt || "").toUpperCase().replace(/[\s\-_.]/g, "").replace(/[I1]/g, "L"); if (s.length !== 10) return null;
  let n = 0; for (const ch of s) { const k = CH.indexOf(ch); if (k < 0) return null; n = n * 32 + k; }
  const T = n % RD_T, P = ((Math.floor(n / RD_T)) ^ (rdH(sec, T, 2) % RD_P)) >>> 0; if (rdH(sec, P, 1) % RD_T !== T) return null;
  const reward = Math.floor(P / 65536); if (!RD_REWARDS.includes(reward)) return null; return { reward, code: s }; }
const CORS = { "access-control-allow-origin": "*", "access-control-allow-methods": "POST, OPTIONS", "access-control-allow-headers": "content-type", "content-type": "application/json" };
const J = (o, st) => new Response(JSON.stringify(o), { status: st || 200, headers: CORS });

export class Codes {
  constructor(state) { this.sql = state.storage.sql; this.sql.exec("CREATE TABLE IF NOT EXISTS used (code TEXT PRIMARY KEY, day TEXT)"); }
  async fetch(req) { const { code } = await req.json();
    if (this.sql.exec("SELECT 1 FROM used WHERE code = ?", code).toArray().length) return J({ e: "used" });
    this.sql.exec("INSERT INTO used (code, day) VALUES (?, ?)", code, new Date().toISOString().slice(0, 10)); return J({ ok: true }); }
}

async function redeem(req, env) {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") return J({ e: "bad" }, 405);
  if (!env.REDEEM_SECRET || !env.CODES) return J({ e: "off" }, 503);
  let body = null; try { body = await req.json(); } catch (_) {}
  const d = rdDecode(env.REDEEM_SECRET, body && body.code); if (!d) return J({ e: "bad" });
  const r = await env.CODES.get(env.CODES.idFromName("codes")).fetch("https://codes/", { method: "POST", body: JSON.stringify({ code: d.code }) });
  const o = await r.json(); return J(o.ok ? { ok: true, reward: d.reward } : o);
}

export default {
  async fetch(req, env) {
    const path = new URL(req.url).pathname;
    if (path === "/redeem") return redeem(req, env);
    if (MEDIA[path]) return serveMedia(req, MEDIA[path]);
    if (path === "/news") return new Response(JSON.stringify(NEWS), { headers: { ...CORS, "cache-control": "public, max-age=300" } });
    if (req.headers.get("Upgrade") !== "websocket") return new Response("ok", { headers: { "content-type": "text/plain" } });
    const hub = env.HUB.get(env.HUB.idFromName("hub"));
    return hub.fetch(req);
  },
};

export class Hub {
  constructor(state) { this.state = state; this.rooms = null; this.queue = [null, null, null]; }

  // rooms: code -> [ws, ws] rebuilt from the sockets' attachments when the object wakes up
  load() {
    if (this.rooms) return;
    this.rooms = new Map(); this.queue = [null, null, null];
    for (const ws of this.state.getWebSockets()) {
      const a = this.att(ws);
      if (a.room) { const r = this.rooms.get(a.room) || []; r.push(ws); this.rooms.set(a.room, r); }
      if (a.q != null && !a.room) this.queue[a.q] = ws;
    }
  }
  att(ws) { try { return ws.deserializeAttachment() || {}; } catch (_) { return {}; } }
  set(ws, a) { try { ws.serializeAttachment(a); } catch (_) {} }
  send(ws, o) { try { ws.send(JSON.stringify(o)); } catch (_) {} }
  newCode() { for (let i = 0; i < 50; i++) { const b = crypto.getRandomValues(new Uint8Array(4)); const c = Array.from(b, x => CH[x & 31]).join(""); if (!this.rooms.has(c)) return c; } return null; }
  other(ws) { const a = this.att(ws), r = a.room && this.rooms.get(a.room); return r ? r.find(x => x !== ws) : null; }

  leave(ws) {
    const a = this.att(ws);
    const qi = this.queue.indexOf(ws); if (qi >= 0) this.queue[qi] = null;
    if (!a.room) { if (a.q != null) this.set(ws, {}); return; }
    const r = (this.rooms.get(a.room) || []).filter(x => x !== ws);
    this.set(ws, {});
    if (!r.length) this.rooms.delete(a.room); else { this.rooms.set(a.room, r); this.send(r[0], { t: "peer", on: false }); }
  }
  enter(ws, code, role) {
    const r = this.rooms.get(code); if (!r || r.length >= 2) return false;
    this.leave(ws); r.push(ws); this.set(ws, { room: code, role });
    const o = this.other(ws); if (o) { this.send(o, { t: "peer", on: true }); this.send(ws, { t: "peer", on: true }); }
    return true;
  }

  async fetch(req) {
    const pair = new WebSocketPair();
    this.state.acceptWebSocket(pair[1]);
    this.set(pair[1], {});
    return new Response(null, { status: 101, webSocket: pair[0] });
  }

  async webSocketMessage(ws, txt) {
    this.load();
    if (typeof txt !== "string" || txt.length > MAX_MSG) return;
    let m; try { m = JSON.parse(txt); } catch (_) { return; } if (!m || typeof m !== "object") return;
    if (m.t === "create") {
      const c = this.newCode(); if (!c) return this.send(ws, { t: "err", e: "busy" });
      this.rooms.set(c, []); this.enter(ws, c, "host"); return this.send(ws, { t: "room", code: c, role: "host" });
    }
    if (m.t === "join") {
      const c = String(m.code || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4); let r = this.rooms.get(c);
      // v2 (2026-11-11): reconnect ({re:1, role}). A dropped player gets back into the same room: it is recreated if both
      // dropped, and a stale socket of the same role (the phone lost network before the server noticed) is replaced.
      if (m.re && c.length === 4) {
        if (!r) { r = []; this.rooms.set(c, r); }
        const role = m.role === "host" ? "host" : "guest";
        if (r.length >= 2) { const old = r.find(x => x !== ws && this.att(x).role === role); if (old) { this.leave(old); try { old.close(1000, "replaced"); } catch (_) {} r = this.rooms.get(c) || []; if (!this.rooms.has(c)) this.rooms.set(c, r); } }
        if (r.length >= 2) return this.send(ws, { t: "err", e: "full" });
        this.send(ws, { t: "joined", code: c, role }); this.enter(ws, c, role); return;
      }
      if (!r) return this.send(ws, { t: "err", e: "nosuch" }); if (r.length >= 2) return this.send(ws, { t: "err", e: "full" });
      this.send(ws, { t: "joined", code: c, role: "guest" }); this.enter(ws, c, "guest"); return;
    }
    if (m.t === "queue") {
      const d = Math.max(0, Math.min(2, m.diff | 0)); this.leave(ws); const w = this.queue[d];
      if (w && w !== ws && w.readyState === 1) {
        this.queue[d] = null; const c = this.newCode(); if (!c) return this.send(ws, { t: "err", e: "busy" });
        this.rooms.set(c, []);
        this.send(w, { t: "matched", code: c, role: "host" }); this.send(ws, { t: "matched", code: c, role: "guest" });
        this.enter(w, c, "host"); this.enter(ws, c, "guest");
      } else { this.queue[d] = ws; this.set(ws, { q: d }); }
      return;
    }
    if (m.t === "leave") return this.leave(ws);
    if (m.t === "ping") return; // v2: keep-alive from the game, nothing to do
    if (m.t === "msg") { const o = this.other(ws); if (o) this.send(o, { t: "msg", d: m.d }); }
  }

  async webSocketClose(ws) { this.load(); this.leave(ws); try { ws.close(1000, "bye"); } catch (_) {} }
  async webSocketError(ws) { this.load(); this.leave(ws); }
}
