# Personal Undertale and Deltarune appearances

Two optional local faces are installed on this computer:

- **Undertale · Determination**: white battle boxes, the red SOUL, official Sans,
  Papyrus and Toriel portraits, a glinting save point and the barking Annoying Dog.
- **Deltarune · Dark World**: a moving purple battle grid, official Kris, Susie and
  Ralsei battle sprites, coloured party meters and an animated Dark Fountain clock.

Both keep the five-screen layout and render at 128×128 per panel. Every percentage
and bar means **quota used**, not HP remaining or game TP. Each quota window keeps
its own reset countdown. Missing readings show `--` / `UNKNOWN`; cached readings
are marked `OLD` and have a hatched bar. The animation loops in four seconds.
The 240×240 photo-display versions remain static.

The dashboard lists each as **Local**. Preview does not apply it to the device.
The new code is committed locally; this change has not been pushed to GitHub.

## Artwork and provenance

Downloaded artwork and derived sprites live outside the repository at:

`~/.local/share/token-tv/local-games/`

`TOKEN_TV_LOCAL_ART` can override that directory. The default directory contains
`sources/`, `sprites/`, `sources.json` with original URLs and SHA-256 checksums,
and `extraction.json` with crop and background-removal details. The extraction
scripts are saved there for local maintenance. No artwork is downloaded while
rendering or running the service. A face is listed only when all its required
sprite files are present. Keep those files in place while the face is selected.

All source artwork comes directly from official game websites:

- [Undertale Alarm Clock](https://undertale.com/alarmclock/): character portraits.
- [Undertale homepage](https://undertale.com/): the dog and barking-dog images.
- [Deltarune September 2020 update](https://deltarune.com/update-092020/): official
  `c2-01.png` and `c2-04.png` screenshots, from which party sprites are cropped.
- [Deltarune homepage](https://deltarune.com/): the animated Dark Fountain key art.

Game artwork remains © Toby Fox and the games' artists. It is outside Git and
is not included in the repository's software license or redistributed.
Sprites are cropped and uniformly scaled with nearest-neighbour sampling.
The meters, layout, SOUL and save-point animation are drawn by the renderer.

## Checks

```sh
.venv/bin/python -B -m unittest discover -s tests -v
node --check token_tv/web/app.js
```

`tests/test_local_games.py` uses synthetic artwork in temporary directories to
check optional installation, all panel roles, unknown/zero/stale readings,
local-only loading and native animation payloads. The Times Gate browser checks
include every installed appearance and verify the complete five-screen strip.
