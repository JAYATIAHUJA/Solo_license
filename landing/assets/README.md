# Landing page assets — exact specs

The landing page works beautifully with **no files here** (the hero falls back
to a coded animated grid + the live autonomy-dial showpiece). Drop these in to
enrich it — the page auto-detects them and only shows the video once it loads.

## 1. Hero background video (optional, recommended)

A dark, slow, seamless loop that sits *behind* the hero text at ~28% opacity.

| File | Spec |
|---|---|
| `hero.mp4` | 1920×1080 (or 2560×1440), H.264, ~10–20 s **seamless loop**, muted, **≤ 6 MB** |
| `hero.webm` | same source exported as VP9/WebM (smaller; loaded first) |
| `hero-poster.jpg` | first frame, 1920×1080, used while the video buffers |

**Art direction:** keep it *dark and low-contrast* (deep navy `#031b36`), so the
cream text stays readable. Abstract motion reads best — think slow particle
field, flowing grid/mesh, data-stream lines, or a slow dolly over a dark
dashboard. Avoid bright frames and hard cuts. Signature accent to echo: the
red-orange `#ff2c17`.

## 2. Social preview image (optional)

| File | Spec |
|---|---|
| `og.jpg` | 1200×630, the share-card image for links (Slack, X, LinkedIn) |

## Palette (for whoever makes the media)

| Token | Hex | Use |
|---|---|---|
| navy | `#031b36` | background |
| cream | `#fdffee` | text |
| red-orange | `#ff2c17` | accent / "detection" |
| aqua | `#b6ffff` | "clean / earned" accent |

Fonts used on the page: **Space Grotesk** (headings), **Inter** (body),
**Space Mono** (labels), **Instrument Serif** (italic accents) — all Google
Fonts, already linked.
