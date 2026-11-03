# One More Floor Escape · App Store

Everything for the App Store page lives here. The workflow **App Store (ficha)** (`.github/workflows/appstore.yml`)
reads this folder and fills App Store Connect through the API with the same secrets as TestFlight.

| Folder | What |
|---|---|
| `metadata/<locale>/` | name, subtitle, description, keywords, promotional text, URLs (en-US, es-ES, es-MX) |
| `metadata/default/` | copyright and notes for App Review |
| `screenshots/<locale>/` | `iphone-*.png` 1290x2796 (6.9"/6.7" slot) and `ipad-*.png` 2048x2732 (13" slot) |
| `previews/<locale>/` | App Previews: `iphone-1.mp4` 886x1920 and `ipad-1.mp4` 1200x1600, 30 fps, about 25 s, with music |
| `site/` | privacy and support pages (fill in CONTACT_EMAIL, then host them) |
| `scripts/asc_publish.py` | the API script the workflow runs |

All captures are real gameplay of Escape v62, recorded frame by frame in a headless browser.

## Order of steps
1. One-time items only the account owner can do (see the thread): agreements, contact email, privacy/support hosting, price, App Privacy answers.
2. New build with version `1.0.0` and `store` checked (hides PRUEBAS): TestFlight (Escape) workflow.
3. Run **App Store (ficha)** with version `1.0.0`, `submit` off. Check the page in App Store Connect.
4. When the owner says go: run it again with `submit` on.

## Answers used
- Category: Games, subcategories Action and Arcade.
- Age rating: only "Cartoon or Fantasy Violence: infrequent/mild"; everything else none/no (expected 9+).
- App Privacy (set by hand in App Store Connect, the API can't): **Data Not Collected**.
- Export compliance: already declared in the build (no non-exempt encryption).
- Content rights: the game uses a CC0 asset pack, so answer "yes, it contains third-party content and I have the rights".
