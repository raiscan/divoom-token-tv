# Divoom Times Gate

This adaptation renders each of the five 128×128 LCD screens at its native resolution.
Claude and Codex usage come from the existing TokenTV providers. It uploads JPEG pictures
using the local Divoom `/post` API; no firmware flashing or Divoom account password is needed.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/token-tv start --device-type times-gate --device-url 192.168.0.120 \
  --timezone Europe/London --config ~/.config/token-tv/times-gate.json
```

Substitute your device address and timezone. The Times Gate must already be set up in the
Divoom app, online and reachable from this computer. `start --yes` accepts the signed-in
provider accounts automatically. Setup never overwrites an existing config; device type and
timezone flags are used only when creating it.

Each reported quota window gets its own panel. With two windows each from Claude and Codex,
the arrangement is Claude short / Claude week / local clock / Codex short / Codex week.
Providers sometimes report fewer windows (for example, only a weekly Codex quota); a spare
panel shows update status. Missing data remains unknown, and cached readings say OLD.
More than four usage windows rotate in groups every five minutes, without merging accounts.

The dashboard at http://127.0.0.1:8787 shows the same five panels in **Clock display**.
All seven appearances have native layouts: Pixel, Digital, Neon, Pixel Retro, Sci-Fi HUD,
Space and Game Boy. Pixel Retro's landscapes are uniformly scaled and cropped around the
sunset and moon, preserving their proportions. Digital uses the original LCD numerals, Neon
uses glowing frames, HUD uses its angled grid, and Game Boy uses the four-shade LCD palette
from the bundled example. Space animates stars and helmeted mascots in a four-second loop.

The gallery and clock preview show the complete 640×128 strip. Selecting **Preview** never
changes the physical display; **Apply to clock** sends your choice. This installation keeps
Pixel Retro selected. Source Game Boy images use exactly four shades; JPEG transport can
introduce small colour variations on the physical LCDs.
Provider usage refreshes every five minutes, while the clock and reset timers update every
minute. Unchanged panels are resent after five minutes to recover from missed updates;
a changed device picture ID triggers immediate reassertion on the next minute tick.

The transport follows the working JPEG/LCD targeting approach in
[Divoom Gaming Gate](https://github.com/adiastra/divoom-gaming-gate).
HTTP success alone is insufficient: the adapter also checks Divoom's `error_code`.
The service can report successful delivery, but the hardware itself has no screenshot API;
confirm that the panels are visible on the physical device.

## This installation

The stable checkout is `/home/farrell/code/projects/divoom-token-tv` and its private remote
is https://github.com/raiscan/divoom-token-tv. The original repository remains the `upstream`
remote. Runtime account metadata and state are outside Git under `~/.config/token-tv/`.
Only images and percentages go to the device. The dashboard listens on localhost.

A user service named `token-tv-times-gate.service` starts with your user session and restarts
on failure. The computer must remain powered on and connected to the home network.

```sh
systemctl --user status token-tv-times-gate
systemctl --user restart token-tv-times-gate
journalctl --user -u token-tv-times-gate -n 30
```

To stop the display controller and restore the saved channel selections:

```sh
systemctl --user disable --now token-tv-times-gate
cd /home/farrell/code/projects/divoom-token-tv
.venv/bin/token-tv run --config ~/.config/token-tv/times-gate.json --restore-display
```

The restore backup is bound to this device URL. It preserves the previous channel selection,
but cannot download or recreate an overwritten custom picture. If needed, reselect the saved
face in the Divoom app. Brightness, Wi-Fi and ambient lighting settings are untouched.
If the clock's IP changes, edit `device_url` in the config and restart the service. A DHCP
reservation for the device avoids that problem.

## Verification

```sh
.venv/bin/python -B -m unittest discover -s tests -v
node --check token_tv/web/app.js
```

`tests/test_times_gate.py` uses a local HTTP device fixture: native JPEG and animated GIF payloads, screen targeting,
picture ID ordering, reboots, periodic recovery, device error handling, backup identity,
unknown/stale data, overflow rotation, configuration validation and dashboard preview. `tests/test_times_gate_faces.py` covers
artwork proportions, unknown/stale states across appearances, the Game Boy palette, animated
previews and the full Game Boy preview/apply flow. `scripts/test_times_gate_browser.cjs` checks
the wide gallery, all seven previews and responsive layouts against a local fixture.
