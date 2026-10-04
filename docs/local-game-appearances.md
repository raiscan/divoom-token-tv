# Personal Undertale and Deltarune appearances

Two optional local faces are installed on this computer:

- **Undertale · Determination**: white battle boxes, the red SOUL, official Sans,
  Papyrus and Toriel portraits, a glinting save point and the barking Annoying Dog.
- **Deltarune · Dark World**: a moving purple battle grid, official Kris, Susie and
  Ralsei battle sprites, coloured party meters and an animated Dark Fountain clock.

Both keep the five-screen layout and render at 128×128 per panel. Every percentage
and bar means **quota used**, not HP remaining or game TP. Each quota window keeps
its own reset countdown. Missing readings show `--` / `UNKNOWN`; cached readings
are marked `OLD` and have a hatched bar. The original faces loop in four seconds.
The 240×240 photo-display versions remain static. Deltarune uses horizontal quota
bars only; its former duplicate vertical meter has been removed.

This installation now uses **one screen per subscription**: Claude's 5-hour and
weekly windows share screen 1, and Codex's windows share screen 2. Each row has
its own horizontal **USED** bar and reset countdown. The two bars are stacked at the
bottom with **5H** and **1W** aligned at the far left. The percentages and reset times
follow the same top-to-bottom order. Unreported windows stay `--`.
Reset timers use a small looping-clock icon. Larger original battle sprites perform
three four-second clips in a twelve-second loop, choosing a shuffled action order
for each account each minute. The same account/minute selects the same sequence
for the physical device and preview. Actions include idle, ACT, defend and Ralsei's
pacify spell. Native animations use two frames per second to keep the complete
five-screen set within the clock's memory. Extra weapon/spell effects are clipped to the portrait area at the
original proportions, keeping the character readable without covering the quota.
Screen 3 is the Dark Fountain clock, screen 4 is Ralsei's party status, and screen 5
is Elnina and Lanino's live weather broadcast. Additional accounts rotate as whole
subscriptions, with three available account positions when weather occupies screen 5.

## Elnina and Lanino weather

Their animated broadcast matches the existing purple battle grid and pixel lettering.
The original battle sprites flank a miniature forecast arena. The game's actual
forecast symbols show sun, moon, rain and snow; an animated cloud handles cloudy,
foggy and stormy conditions. Weather projectiles travel inward and turn into hearts,
echoing the battle. The weather symbol follows the real forecast, while unknown
conditions show `--`. Effects stay inside the arena, above the readable forecast.
The original five-pose website animation remains a fallback when the optional battle
assets are absent.
It alternates every four seconds between current conditions and tomorrow's high/low
temperatures and daily maximum precipitation probability for **Poole, Dorset, UK**.
Temperatures are Celsius. Missing readings are `--`; a cached forecast after a failed
refresh or an aged reading is marked **OLD**. Forecast days are selected by their
local dates, so yesterday's cached data cannot become tomorrow's forecast.

Weather comes from [Open-Meteo](https://open-meteo.com/en/docs) and refreshes with the
normal five-minute polling cycle. The model's current temperature is not a measurement
from the clock. The five-panel preview shows the same weather animation as the device.
The custom forecast replaces the active Weather ONE face on screen 5 while the
computer runs; the original Divoom face and saved layout remain available in the app.
The service no longer reselects the built-in Weather ONE face during quota uploads.

Use `--times-gate-layout accounts --times-gate-panels 1,2,3,4,5` with
`--forecast-city Poole --forecast-latitude 50.71429 --forecast-longitude -1.98458`.
Do not combine the custom forecast with `--weather-clock`; that would select a native
face over the uploaded animation. The phone token remains in its private file.

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

The original weather, fountain and static party artwork comes from official game
websites. Additional action frames are original game sprites from the **PC / Computer**
sprite sheets at The Spriters Resource, separate from its **Custom / Edited** category.

- [Undertale Alarm Clock](https://undertale.com/alarmclock/): character portraits.
- [Undertale homepage](https://undertale.com/): the dog and barking-dog images.
- [Deltarune September 2020 update](https://deltarune.com/update-092020/): official
  `c2-01.png` and `c2-04.png` screenshots, from which party sprites are cropped.
- [Deltarune homepage](https://deltarune.com/): the animated Dark Fountain key art.
- [Deltarune's official weather page](https://deltarune.com/weather/): the transparent
  Elnina and Lanino sprite animation (`weather.gif`, five original poses). Frames are
  extracted without repainting and uniformly scaled with nearest-neighbour sampling.
- [Elnina & Lanino battle sprites](https://www.spriters-resource.com/pc_computer/deltarune/asset/273061/)
  and [battle attacks / forecast symbols](https://www.spriters-resource.com/pc_computer/deltarune/asset/516984/):
  original Chapter 3 game sprites. The game's forecast-card symbols, moon and cloud
  mascots, and rain/crystal/heart projectiles guide the arena design. Exact source
  crops and background removal are recorded in `weather-battle-extraction.json`;
  `extract-weather-battle.py` keeps the extraction repeatable outside Git. Background
  removal on the host sprites is limited to boundary-connected background pixels,
  preserving internal white/black details.
- [Kris](https://www.spriters-resource.com/pc_computer/deltarune/asset/110448/),
  [Susie](https://www.spriters-resource.com/pc_computer/deltarune/asset/110471/) and
  [Ralsei](https://www.spriters-resource.com/pc_computer/deltarune/asset/110469/): original
  Chapters 1–2 battle animations. Original sheets, their URLs/checksums, extracted
  frames, action sequences and exact cell crops remain in the local artwork directory,
  in `sources.json`, `party-actions.json` and `party-actions-extraction.json`.

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
local-only loading and native animation payloads. `tests/test_weather.py` covers
forecast normalization, zero/unknown/stale states, outages, date selection, private
location-bound caching, paired quota windows, account rotation, and the full 16-frame
weather transport and preview, and shuffled original action clips with a 48-frame
combined preview that preserves both native loop timings. The Times Gate browser checks
include every installed appearance and verify the complete five-screen strip.
Battle-weather checks cover condition-specific symbols, night/unknown states,
fallback assets and a numerical forecast region untouched by animated effects.
