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

export default {
  async fetch(req, env) {
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
      const c = String(m.code || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4); const r = this.rooms.get(c);
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
    if (m.t === "msg") { const o = this.other(ws); if (o) this.send(o, { t: "msg", d: m.d }); }
  }

  async webSocketClose(ws) { this.load(); this.leave(ws); try { ws.close(1000, "bye"); } catch (_) {} }
  async webSocketError(ws) { this.load(); this.leave(ws); }
}
