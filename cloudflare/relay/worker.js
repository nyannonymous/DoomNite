// DoomNite relay: one Durable Object per room, forwarding opaque BINARY
// frames between exactly two sockets. This is the SkyJump3D trick
// (cloudflare/worker.js's `Room` class, same project, different game)
// applied to Zandronum's raw UDP traffic instead of JSON game state:
// both players connect OUTBOUND to this Worker over wss://, so neither
// one ever needs a port forward, UPnP, a VPN (Tailscale), or to survive
// NAT hole-punching (tools/punch.py's job, which this does NOT replace --
// see tools/wsrelay.py's docstring for when to use which).
//
// Deliberately NOT like SkyJump3D's Room: that one parses JSON, stamps a
// sender id, and fans out to up to 6 peers. This one never looks inside
// the frame (Zandronum's packets are not JSON and must arrive byte-exact),
// and caps a room at 2 sockets because Zandronum's UDP relationship here
// is strictly host<->one joiner per PunchRelay-equivalent tunnel. A LAN
// party of >2 still works today over NN/STUN/direct; this relay is only
// the "nothing else worked" tier for a single remote friend.
const MAX_ROOM = 2;
const IDLE_CLOSE_MS = 10 * 60 * 1000; // no bytes either direction in 10 min -> close

export class UdpRoom {
  constructor(ctx) {
    this.ctx = ctx;
  }

  async fetch(request) {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('expected websocket', { status: 426 });
    }
    const live = this.ctx.getWebSockets();
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    if (live.length >= MAX_ROOM) {
      this.ctx.acceptWebSocket(server);
      server.close(1000, 'room full');
      return new Response(null, { status: 101, webSocket: client });
    }

    const slot = live.some((w) => w.deserializeAttachment()?.slot === 0) ? 1 : 0;
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({ slot, lastSeen: Date.now() });
    this.ctx.storage.setAlarm(Date.now() + IDLE_CLOSE_MS).catch(() => {});
    return new Response(null, { status: 101, webSocket: client });
  }

  // A room nobody is using (the Python bridge crashed, or the game ended
  // without a clean close) should not sit open forever -- close anything
  // that has not sent a byte in IDLE_CLOSE_MS and let the DO evict itself.
  async alarm() {
    const now = Date.now();
    let stillOpen = false;
    for (const ws of this.ctx.getWebSockets()) {
      const last = ws.deserializeAttachment()?.lastSeen ?? 0;
      if (now - last >= IDLE_CLOSE_MS) {
        try {
          ws.close(1000, 'idle');
        } catch {}
      } else {
        stillOpen = true;
      }
    }
    if (stillOpen) await this.ctx.storage.setAlarm(now + IDLE_CLOSE_MS);
  }

  // Binary frames only: forward verbatim to the other socket in the room,
  // if one is connected. No peer yet -> drop, same as a UDP packet thrown
  // at an address nobody is listening on. Text frames are treated as
  // keepalive pings and are not forwarded (the client only sends them to
  // keep the Cloudflare connection from idling out; Zandronum never sees
  // them either way since punch.py-style PUNCH_MAGIC filtering already
  // happens locally, not here).
  webSocketMessage(ws, message) {
    if (typeof message === 'string') return;
    const att = ws.deserializeAttachment() || {};
    att.lastSeen = Date.now();
    ws.serializeAttachment(att);
    for (const other of this.ctx.getWebSockets()) {
      if (other === ws) continue;
      try {
        other.send(message);
      } catch {
        /* peer gone; next message will no-op the same way */
      }
    }
  }

  webSocketClose(ws) {
    for (const other of this.ctx.getWebSockets()) {
      if (other !== ws) {
        try {
          other.close(1000, 'peer left');
        } catch {}
      }
    }
  }

  webSocketError(ws) {
    this.webSocketClose(ws);
  }
}

const json = (o) =>
  new Response(JSON.stringify(o), {
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/relay') {
      const room = (url.searchParams.get('room') || '').replace(/[^\w-]/g, '').slice(0, 32);
      if (!room) return json({ error: 'room required' });
      return env.ROOMS.get(env.ROOMS.idFromName(room)).fetch(request);
    }
    if (url.pathname === '/health') return json({ ok: true });
    return new Response('doomnite relay', { status: 200 });
  },
};
