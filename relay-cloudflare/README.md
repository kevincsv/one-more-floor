# Duel relay (Cloudflare)

Tiny WebSocket relay for the One More Floor Escape duel mode. A Worker plus one Durable Object.
It only forwards messages between the two players of a room: no accounts, no storage, no logs.

Protocol: `create` · `join {code}` · `queue {diff}` · `leave` · `msg {d}`; replies `room`, `joined`,
`matched {code, role}`, `peer {on}`, `msg {d}`, `err {e: nosuch|full|busy}`.

Deploy: Cloudflare dashboard, Workers & Pages, Create, Import a repository, pick this repo and set the
root directory to `relay-cloudflare`. Or locally: `npm install && npx wrangler deploy`.
The game connects to `wss://omf-duel-relay.<subdomain>.workers.dev`.
