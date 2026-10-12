# Single library registry (no duplicate downloads across output folders)

## Objective
Know whether a song already exists anywhere in the user's library, whatever output folder is
selected, and let the user choose to skip or re-download existing songs.

## Problem / why
yt-dlp's download archive (`.downloaded-audio.txt` / `.downloaded-video.txt`) lives in each output
folder (pista/core/downloader.py ARCHIVES, `download_archive`), so the same album downloaded with
two output folders (Peso Pluma / Tito Double P) was downloaded twice. The archive stores only ids,
so a deleted/moved file still counts as "already downloaded".

## Design (approved by user 2026-10-11)
- Registry file in the user config dir: per format, video id → absolute file path. Thread-safe
  writes (downloads run in worker threads); atomic save.
- Recorded after every successful download (the real path download() returns).
- First run (no registry yet): bootstrap in the background by scanning every folder that contains a
  legacy `.downloaded-*.txt` (and the current output folder): read the YouTube URL embedded in each
  file (MP3: ID3 `TXXX:purl` / `TXXX:comment`, e.g. https://www.youtube.com/watch?v=Wz84N4A6S6Q;
  MP4: check what yt-dlp's EmbedMetadata writes — verify on a real/fixture file) → id → path.
- "Exists" = registry has the id for this format AND the file is still at that path. Missing file →
  treated as not existing (downloads again).
- Confirm dialog: "N canciones ya existen en tu biblioteca" with two actions:
  "Descargar sin las existentes" (primary, default) and "Descargar todas" (re-downloads existing
  ones into the current output folder).
- Re-download must actually happen: the per-folder yt-dlp archive must not silently skip it.
- Known limitation: a file moved in Finder is seen as missing (re-downloaded). Re-scan by embedded
  URL could fix it later.

## Constraints
- Spanish UI copy, English code; stdlib + mutagen (already a dependency); no new deps.
- Never block the UI: bootstrap and existence checks off the event loop or cheap.

## Tasks
- [x] T1 core registry + bootstrap scan + download records it + plan uses it — delegated writer.
- [x] T2 confirm dialog: existing count + two buttons; "todas" really re-downloads — delegated writer
      (may be the same writer if small).

## Progress / evidence
- User (2026-10-11): merge the existing per-folder archives into the single registry (bootstrap
  covers it); work stays on local `main` (no separate branch).
- T1+T2 done: pista/core/registry.py (library.json {fmt:{id:path}}, lock + atomic save, existing()
  checks is_file, bootstrap reads MP3 TXXX:purl/comment and MP4 ©cmt); download() no longer uses
  download_archive; registry recorded via recording() wrapper in app.py; plan include_existing;
  confirm dialog "N canciones ya existen…" + "Descargar sin las existentes" / "Descargar todas".
  Legacy archive used until bootstrap finishes. RED: ModuleNotFoundError / TypeError; GREEN: pytest
  334 passed. Dry run: 358 audio ids from 532 files in 0.3 s, all 345 legacy ids found.
  Limitation: Pista's MP4s have no embedded URL (no metadata step for video) → old MP4s not imported.
  Overwrite: yt-dlp defaults (MP3 re-extracts over same path; existing merged MP4 kept).
- Review (19 files) approved with warnings, all fixed: video keeps legacy archive ids (old MP4s
  have no URL); record() always persists, "bootstrapped" flag in file → failed scan retried next
  start; corrupt JSON backed up and rebuilt, invalid entries dropped; bootstrap never scans home/
  root/mounts, 20000-path cap; recording() tested through a real BatchRunner. pytest 337 passed.
- Review (19 files) approved; fixed: legacy audio ids count when the registry doesn't know the song
  (bounded scan may miss folders), known ids decided by path (R3-001); failed bootstrap no longer
  marks ready, legacy archives keep counting that run (R3-002). Noted: confirm dialog stats files on
  the event loop (R3-003). pytest 337 passed.

## Next step
User manual check; push when the user says.
