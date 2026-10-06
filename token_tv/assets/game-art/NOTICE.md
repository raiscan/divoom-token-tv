# Undertale and Deltarune fan-theme artwork

These appearances use original **UNDERTALE** and **DELTARUNE** characters and
artwork, © Toby Fox, Temmie Chang and the games' artists. Character names and game
names belong to their respective rights holders.

TokenTV's Undertale and Deltarune appearances are an **unofficial, non-commercial
fan project**. This repository is not affiliated with, endorsed by, or sponsored by
Toby Fox, the game teams, Fangamer, or Divoom. Inclusion here does not assert their
permission or an artwork redistribution license.

## Separate from the software license

The repository's MIT license applies to the TokenTV software. It does **not**
license these original game images or grant permission to relicense, sell, or
otherwise exploit the artwork. Original artwork ownership remains with its
rights holders. The fan project's intended use is displaying AI quota information,
clock/status panels, and weather on a personal desk display.

The [official fan policies](https://deltarune.com/help/#policy) provide context for
fan merchandise and music; they do not specifically authorize distributing game
sprites in software. This notice does not claim they do.

## Sources and transformations

- Character portraits and the Annoying Dog come from
  [Undertale's official website](https://undertale.com/alarmclock/).
- The Dark Fountain, static party sprites, and original weather-host animation
  come from [Deltarune's official website](https://deltarune.com/), its
  [September 2020 update](https://deltarune.com/update-092020/), and its
  [weather page](https://deltarune.com/weather/).
- Battle actions, DOWN poses, Darkner Gerson, Elnina and Lanino, and forecast
  symbols are original game sprites from the PC / Computer Deltarune sheets on
  [The Spriters Resource](https://www.spriters-resource.com/pc_computer/deltarune/),
  not its Custom / Edited category. Individual source pages and file checksums
  are preserved in `sources.json` and the extraction records.

`sprites/` contains the selected frames used by the renderers. Complete source
sheets, downloaded screenshots, and inspection images are not bundled. Paths to
`sources/` in provenance records identify original inputs, not packaged files.
Sprites are cropped, have recorded background removal, and are uniformly scaled
with nearest-neighbour sampling. `sprite-checksums.json` records SHA-256 checksums
for every bundled PNG. The software draws the layouts, quota bars, and effects.

Provenance records: `sources.json`, `extraction.json`,
`party-actions-extraction.json`, `party-downed-extraction.json`,
`weather-battle-extraction.json`, and `gerson-extraction.json`.
`party-actions.json` and `party-downed.json` define the runtime animation sequences.
