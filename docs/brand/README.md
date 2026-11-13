# gruntly brand kit

Logo: **one big agent, a few small ones.** A charcoal terminal-prompt head (the paid agent) with three small orange heads (the smaller models doing the grunt work).

Tagline: **Hand the grunt work to small models.**

Everything here is final. Use the files as they are. Do not redraw, recolour, retype or add effects (no gradients, glows, shadows, outlines).

## Which file for what

| Need | File |
|---|---|
| README header (light and dark GitHub themes) | `svg/horizontal-color.svg` + `svg/horizontal-color-on-dark.svg` |
| Docs site header / nav | `svg/horizontal-color.svg` (light bg) or `svg/horizontal-color-on-dark.svg` (dark bg) |
| Docs site favicon | `favicon/favicon.svg`, `favicon/favicon.ico`, `favicon/apple-touch-icon.png` |
| GitHub org / repo avatar | `github/avatar-500.png` (1024 version also provided) |
| GitHub social preview (Settings > Social preview) | `github/social-preview-1280x640.png` |
| Square icon, app or plugin listing | `svg/icon-color.svg` on light, `svg/icon-color-on-dark.svg` on dark, or `png/icon-color-512.png` |
| Centred / square placement | `svg/stacked-color.svg`, `svg/stacked-color-on-dark.svg` |
| Single-colour print, stamps, one-colour UI | `svg/*-dark.svg` (charcoal) or `svg/*-light.svg` (cream) |
| Raster fallbacks | `png/` (icon 16 to 1024, lockups at about 1050px wide) |

Naming: `color` = charcoal + orange on a light background. `color-on-dark` = cream + orange on a charcoal background. `dark` = all charcoal. `light` = all cream.

## README header snippet

```html
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/svg/horizontal-color-on-dark.svg">
    <img alt="gruntly" src="docs/brand/svg/horizontal-color.svg" height="64">
  </picture>
</p>
<p align="center"><b>Hand the grunt work to small models.</b></p>
```

## Docs site `<head>`

```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#23252B">
<meta property="og:image" content="/social-preview-1280x640.png">
<meta name="twitter:card" content="summary_large_image">
```

Copy `favicon.ico`, `favicon.svg`, `apple-touch-icon.png` to the site root. `favicon-16/32/48.png` are only needed if you prefer PNG links.

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

Terminal (truecolor): orange `\x1b[38;2;255;106;19m`, cream `\x1b[38;2;244;241;234m`, reset `\x1b[0m`. 256-colour fallback for orange: `\x1b[38;5;202m`.

## Type

- Wordmark: outlined monospace glyphs inside the SVGs. Never retype it.
- Site headings: Bitter 800, tight tracking (-0.035em). Site labels, code and UI: IBM Plex Mono. Both are on Google Fonts.
- Always lowercase "gruntly" in running UI and the wordmark. Sentence case elsewhere.

## Rules

- Minimum size: icon 16px, horizontal lockup 96px wide, stacked lockup 64px wide.
- Clear space: at least the width of one small orange head on every side.
- Use `color` variants on cream or white, `color-on-dark` on charcoal or near-black. On any other background (photos, orange, mid-grey) use the one-colour files.
- Do not stretch, rotate, reorder the small heads, change the orange, or put the mark inside a circle (the GitHub avatar is already square-safe: it is cropped to a circle by GitHub with the mark inside the safe area).
- Raster favicons and the avatar sit on a charcoal tile so they read in both light and dark browser tabs.
- Avoid boar, pig or warthog imagery (an unrelated tool called Grunt uses a boar). Avoid sparkles, circuits and gradients.

## Notes

- `svg/social-preview.svg` uses live `<text>`, so it depends on installed monospace fonts. Use the PNG for uploads.
- The social preview (`github/social-preview-1280x640.png`, source `svg/social-preview.svg`) carries two lines, the maintainer's choice: the big one, **"Pay big agent prices only for big agent work."**, and the small grey one, "open-source · same quality, fewer paid tokens". The tagline everywhere else (README, `brand.json`, the package description) stays "Hand the grunt work to small models." The numbers behind the image's lines, with where they hold and where they do not, are in `docs/where-delegation-wins.md`.
- This folder is the kit without the site design reference (`reference/gruntly-site.html`) and the terminal demo page (`demo/terminal-demo.html`): both are website material and live with the website. Keep the full kit wherever the design files live.
- The SVGs are clean (no metadata, no external references, no fonts) and safe to inline.
- Logo source: concept 29 in the logo explorations.
