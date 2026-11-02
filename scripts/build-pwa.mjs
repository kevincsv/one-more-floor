// Genera una PWA instalable (Safari → Compartir → Añadir a pantalla de inicio) en la carpeta pwa/.
// Uso: node scripts/build-pwa.mjs [ruta/al/juego.html]
import { execFileSync } from "node:child_process";
import { cp, readFile, writeFile, rm, readdir } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
execFileSync(process.execPath, [path.join(root, "scripts", "sync-game.mjs"), ...process.argv.slice(2)], { stdio: "inherit" });
const out = path.join(root, "pwa");
await rm(out, { recursive: true, force: true });
await cp(path.join(root, "www"), out, { recursive: true });
await cp(path.join(root, "pwa-assets"), out, { recursive: true });

const version = new Date().toISOString().replace(/\D/g, "").slice(0, 12);
await writeFile(path.join(out, "manifest.webmanifest"), JSON.stringify({
  name: "One More Floor", short_name: "One More Floor", start_url: "./", scope: "./",
  display: "fullscreen", orientation: "any", background_color: "#100e1a", theme_color: "#100e1a",
  icons: [192, 512].map((n) => ({ src: `icon-${n}.png`, sizes: `${n}x${n}`, type: "image/png", purpose: "any maskable" })),
}, null, 2));

const files = ["./", "index.html", "manifest.webmanifest", "icon-180.png", "icon-192.png", "icon-512.png",
  ...(await readdir(path.join(out, "fonts")).catch(() => [])).map((f) => `fonts/${f}`)];
await writeFile(path.join(out, "sw.js"), `const C="omf-${version}";const F=${JSON.stringify(files)};
self.addEventListener("install",e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(F)));self.skipWaiting();});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))));self.clients.claim();});
// Red primero (así siempre ves la última versión si hay internet), caché si no hay conexión.
self.addEventListener("fetch",e=>{if(e.request.method!=="GET")return;e.respondWith(fetch(e.request).then(r=>{const cl=r.clone();caches.open(C).then(c=>c.put(e.request,cl));return r;}).catch(()=>caches.match(e.request,{ignoreSearch:true})));});
`);

let html = await readFile(path.join(out, "index.html"), "utf8");
html = html.replace(/<head([^>]*)>/i, `<head$1>
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">`);
html = html.replace(/<\/body>/i, `<script>if("serviceWorker" in navigator)addEventListener("load",()=>navigator.serviceWorker.register("sw.js"));</script>\n</body>`);
await writeFile(path.join(out, "index.html"), html);
console.log("PWA lista en", out);
