# gruntly brand kit

Logo: **one big agent, a few small ones.** A charcoal terminal-prompt head (the paid agent) with three small orange heads (the local agents doing the grunt work).

Tagline: **Hand the grunt work to your local model.**

Everything here is final. Use the files as they are. Do not redraw, recolour, retype or add effects (no gradients, glows, shadows, outlines).

## Which file for what

| Need | File |
|---|---|
| README header (light and dark GitHub themes) | `svg/horizontal-color.svg` + `svg/horizontal-color-on-dark.svg` |
| Docs site header / nav | `svg/horizontal-color.svg` (light bg) or `svg/horizontal-color-on-dark.svg` (dark bg) |
| Docs site favicon | `favicon/favicon.svg`, `favicon/favicon.ico`, `favicon/apple-touch-icon.png` |
| GitHub org / repo avatar (upload by hand in Settings) | `github/avatar-500.png` |
| GitHub social preview (repo Settings > Social preview, upload by hand) | `github/social-preview-1280x640.png` |
| Square icon, app or plugin listing | `svg/icon-color.svg` on light, `svg/icon-color-on-dark.svg` on dark, or `png/icon-color-512.png` |

Naming: `color` = charcoal + orange on a light background. `color-on-dark` = cream + orange on a charcoal background.

This folder is the trimmed copy of the full kit. The one-colour variants, stacked lockups, other PNG sizes and the site design reference were left out on purpose; keep the full kit wherever the design files live.

## Colour

| Name | Hex | Use |
|---|---|---|
| Charcoal | `#23252B` | Mark, wordmark, dark backgrounds, body text on light |
| Safety orange | `#FF6A13` | The three small heads, highlights, buttons on hover. Fills only, not small text on light |
| Cream | `#F4F1EA` | Light background, mark on dark |
| Sand | `#E7E2D6` | Panels and slots on cream |
| Orange text | `#B84300` | Orange-ish text or labels on cream (passes contrast) |
| Grey text | `#4a4d55` | Secondary text on cream |
| Rule | `#CFC9BA` | Dividers on cream |

Tokens are also in `tokens.css` and `brand.json`.

## Type

- Wordmark: outlined monospace glyphs inside the SVGs. Never retype it.
- Site headings: Bitter 800, tight tracking (-0.035em). Site labels, code and UI: IBM Plex Mono. Both are on Google Fonts.
- Always lowercase "gruntly" in running UI and the wordmark. Sentence case elsewhere.

## Rules

- Minimum size: icon 16px, horizontal lockup 96px wide.
- Clear space: at least the width of one small orange head on every side.
- Use `color` variants on cream or white, `color-on-dark` on charcoal or near-black. On any other background (photos, orange, mid-grey) use a one-colour file from the full kit.
- Do not stretch, rotate, reorder the small heads, change the orange, or put the mark inside a circle (the GitHub avatar is already square-safe: GitHub crops it to a circle with the mark inside the safe area).
- Raster favicons and the avatar sit on a charcoal tile so they read in both light and dark browser tabs.
- Avoid boar, pig or warthog imagery (an unrelated tool called Grunt uses a boar). Avoid sparkles, circuits and gradients.
- The SVGs are clean (no metadata, no external references, no fonts) and safe to inline.
