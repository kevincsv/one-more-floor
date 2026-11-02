# One More Floor para iOS (Capacitor)

Envuelve el prototipo HTML5 (`prototipo/one-more-floor.html`) en una app nativa de iOS.
Cada vez que el juego cambie, vuelves a ejecutar el script y tienes la última versión.

## Qué necesitas
- Un Mac con **Xcode** (App Store, gratis) y **Node.js 20+** (`brew install node`).
- Tu **Apple ID** añadido en Xcode → Settings → Accounts.
  - Gratis: instala en tu propio iPhone, la app caduca a los 7 días.
  - Apple Developer Program (99 USD/año): IPA ad hoc, TestFlight y App Store.
- En el iPhone: activar **Modo desarrollador** (Ajustes → Privacidad y seguridad) la primera vez.

## Uso rápido (instalar en tu iPhone)
```bash
cd ios-app
./build-ios.sh          # copia la última versión del juego y abre Xcode
```
En Xcode: proyecto **App** → Signing & Capabilities → elige tu Team, conecta el iPhone y pulsa ▶.

## Generar el archivo .ipa
```bash
TEAM_ID=TU_TEAM_ID ./build-ios.sh ipa                         # IPA de desarrollo
TEAM_ID=TU_TEAM_ID METHOD=app-store-connect ./build-ios.sh ipa # para subir a TestFlight
```
El IPA queda en `build/OneMoreFloor.ipa`. El Team ID está en developer.apple.com → Membership,
o en Xcode → Signing.

## Usar otra versión del juego
```bash
GAME_HTML=~/Descargas/one-more-floor.html ./build-ios.sh
```
Si no indicas nada, busca `game/one-more-floor.html` y luego `../prototipo/one-more-floor.html`.

## Qué hace el script de sincronización
`scripts/sync-game.mjs` copia el HTML a `www/index.html`, añade las etiquetas de iOS (pantalla completa,
sin zoom, zona segura del notch) y descarga las fuentes para que el juego funcione sin internet.

## Sin Mac (desde Windows)
1. El juego vive en `game/one-more-floor.html`. Cada push a `main` lanza dos compilaciones.
2. **Actions → "iOS IPA (sin firmar)"**: descarga `OneMoreFloor-unsigned.ipa` del resultado.
3. Instala **Sideloadly** (sideloadly.io) e iTunes en Windows, conecta el iPhone, arrastra el IPA
   y entra con tu Apple ID: lo firma e instala. Con cuenta gratis caduca a los 7 días (se reinstala igual).
4. La primera vez, en el iPhone: Ajustes → General → VPN y gestión de dispositivos → confiar en tu Apple ID,
   y activar Modo desarrollador.

## Versión web (PWA)
**Actions → "Web (GitHub Pages)"** publica el juego en `https://<usuario>.github.io/<repo>/`.
Ábrelo en Safari → Compartir → **Añadir a pantalla de inicio**: se abre a pantalla completa y funciona sin internet.
Para generarla en local: `node scripts/build-pwa.mjs` (sale en `pwa/`).
