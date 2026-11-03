// Copia la última versión del juego a www/index.html y la adapta para iOS.
// Uso: node scripts/sync-game.mjs [ruta/al/juego.html]
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const candidates = [
  process.argv[2],
  path.join(root, "game", "one-more-floor.html"),
  path.join(root, "..", "prototipo", "one-more-floor.html"),
].filter(Boolean);
const src = candidates.find((p) => existsSync(p));
if (!src) {
  console.error("No encuentro el juego. Pásame la ruta: node scripts/sync-game.mjs ruta/one-more-floor.html");
  process.exit(1);
}

let html = await readFile(src, "utf8");
if (!/<html/i.test(html)) html = `<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n</head>\n<body>\n${html}\n</body>\n</html>\n`;

const head = [
  '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">',
  '<meta name="apple-mobile-web-app-capable" content="yes">',
  '<meta name="mobile-web-app-capable" content="yes">',
  '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">',
  '<meta name="apple-mobile-web-app-title" content="One More Floor">',
  '<meta name="theme-color" content="#100e1a">',
  '<style>html,body{overscroll-behavior:none;-webkit-touch-callout:none;touch-action:none;}</style>',
].join("\n");
html = html.replace(/<meta name="viewport"[^>]*>\s*/gi, "").replace(/<meta charset[^>]*>\s*/gi, "");
html = html.replace(/<head([^>]*)>/i, `<head$1>\n<meta charset="utf-8">\n${head}\n`);

// Fuentes locales para que funcione sin internet (si falla la descarga, se queda la versión online).
const fontLink = html.match(/<link rel="stylesheet" href="(https:\/\/fonts\.googleapis\.com[^"]+)">/);
if (fontLink) {
  try {
    const ua = { headers: { "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1" } };
    let css = await (await fetch(fontLink[1].replace(/&amp;/g, "&"), ua)).text();
    await mkdir(path.join(root, "www", "fonts"), { recursive: true });
    let i = 0;
    for (const url of [...new Set(css.match(/https:\/\/fonts\.gstatic\.com[^)]+/g) || [])]) {
      const name = `f${i++}${path.extname(new URL(url).pathname) || ".woff2"}`;
      await writeFile(path.join(root, "www", "fonts", name), Buffer.from(await (await fetch(url)).arrayBuffer()));
      css = css.split(url).join(`fonts/${name}`);
    }
    html = html.replace(fontLink[0], `<style>\n${css}\n</style>`).replace(/<link rel="preconnect"[^>]*>\s*/gi, "");
    console.log(`Fuentes guardadas localmente (${i} archivos).`);
  } catch (e) {
    console.warn("No pude descargar las fuentes; se usarán online:", e.message);
  }
}

// Capacitor core (registerPlugin): el puente nativo de iOS no lo trae; sin esto los plugins
// (EscapeStore, CloudSave, GameCenter) no responden. Va en línea antes del primer script del juego.
if (!/capacitorExports/.test(html)) {
  const core = (await readFile(path.join(root, "node_modules/@capacitor/core/dist/capacitor.js"), "utf8"))
    .replace(/\n\/\/# sourceMappingURL=.*$/m, "");
  const i = html.search(/<script[\s>]/i);
  html = html.slice(0, i) + "<script>" + core + "</script>\n" + html.slice(i);
  console.log("Capacitor core en línea (registerPlugin)");
}

// Build de tienda (OMF_STORE=1): el juego oculta el menú PRUEBAS, como en Android.
if (process.env.OMF_STORE === "1" && !/window\.OMF_STORE\s*=\s*true/.test(html)) {
  html = html.replace("<script>", "<script>window.OMF_STORE = true;</script>\n<script>");
  console.log("Build de tienda: window.OMF_STORE = true");
}

await mkdir(path.join(root, "www"), { recursive: true });
await writeFile(path.join(root, "www", "index.html"), html);
console.log(`Juego copiado desde ${src} -> www/index.html`);
