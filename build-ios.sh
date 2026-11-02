#!/usr/bin/env bash
# Ejecutar en un Mac con Xcode. Uso:
#   ./build-ios.sh            -> actualiza el juego y abre Xcode (para instalar en tu iPhone con ▶)
#   TEAM_ID=XXXXXXXXXX ./build-ios.sh ipa   -> además genera build/OneMoreFloor.ipa
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install
node scripts/sync-game.mjs "${GAME_HTML:-}"
[ -d ios ] || npx cap add ios
npx cap sync ios

if [ "${1:-}" != "ipa" ]; then npx cap open ios; exit 0; fi

: "${TEAM_ID:?Pon tu Team ID de Apple: TEAM_ID=XXXXXXXXXX ./build-ios.sh ipa}"
METHOD="${METHOD:-debugging}"   # debugging (Apple ID gratis / dev) | release-testing (ad hoc) | app-store-connect (TestFlight)
mkdir -p build
xcodebuild -workspace ios/App/App.xcworkspace -scheme App -configuration Release \
  -archivePath build/App.xcarchive -destination 'generic/platform=iOS' \
  -allowProvisioningUpdates DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic archive
cat > build/ExportOptions.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>$METHOD</string>
  <key>teamID</key><string>$TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
</dict></plist>
PLIST
xcodebuild -exportArchive -archivePath build/App.xcarchive -exportPath build \
  -exportOptionsPlist build/ExportOptions.plist -allowProvisioningUpdates
mv build/App.ipa build/OneMoreFloor.ipa 2>/dev/null || true
echo "Listo: $(pwd)/build/OneMoreFloor.ipa"
