# clay.photography

Personal photo portfolio. Static site, no build step at serve time.

- `photos/` — originals (gitignored, local only)
- `build.py` — reads `photos/`, writes web derivatives into `img/` and all
  metadata into `data.json`
- `index.html` — the whole site: justified grid grouped by subject, lightbox
  with the full EXIF record per frame

## Rebuild after adding or removing photos

    python3 build.py

Subject groupings are the `GROUPS` list at the top of `build.py`, keyed by the
alphabetical index of each file in `photos/`.

## Local preview

    python3 -m http.server 4173

## Deploy

GitHub Pages serves `main` at the root. `CNAME` points it at clay.photography.
