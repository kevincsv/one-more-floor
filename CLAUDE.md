# One More Floor Escape

## Start of every session
1. Read only the status index: `/mnt/project-files/PROJECT_STATUS.md` (current goal,
   work in progress, one line per area).
2. Do NOT read the detail files up front. Open a file in `/mnt/project-files/estado/`
   only when the task touches that area (for example `estado/ios-app-store.md` for a
   TestFlight build, `estado/steam-pc.md` for PC work).
3. Before changing the game, art, UI or anything that ships, also read
   `estado/reglas.md` (standing rules and never-regress checks).

## Keeping status current
- When work starts or finishes, update the "In progress" list in the index.
- Put details, history and links in the matching area file, never in the index.
- Keep the index under 50 lines. New area: add one detail file and one index line.

## Hard rules (summary; full list in estado/reglas.md)
- All art and UI is 8-bit pixel art. No emojis in the game.
- No builds, pushes or store uploads until the user says so.
- Never write personal names or emails in any file, commit or page.
