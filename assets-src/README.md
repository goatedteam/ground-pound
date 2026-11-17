# Source assets

Masters the shipped game assets are made from. The game never loads these; it loads the processed files
under `game/client/public/assets/`.

## audio/

- `music/base_main_riff.mp3`: base-game song (Suno). Shipped as `music/music_base`, loop 18.84 s to 152.42 s.
- `music/fight_title_fight.mp3`: Title Fight song (Suno). Shipped as `music/music_fight`, loop 15.36 s to 179.92 s.
- `sfx/<sound>_<take>.mp3`: raw ElevenLabs takes, one file per take. The prompts are in the audio doc,
  and every take is also in the ElevenLabs flow linked from the developer handoff.

Rebuild the processed sound effects and the base song:

```bash
python game/tools/prepare_audio.py --sfx assets-src/audio/sfx --music base=assets-src/audio/music/base_main_riff.mp3
```

Add `--music fight=assets-src/audio/music/fight_title_fight.mp3` only if you want new loop points for the
Title Fight song: the shipped loop was cut by hand, and the script's search may pick different points.
To replace a sound, drop a new `<sound>_<n>.mp3` here (or remove a take) and re-run the command;
`manifest.json` is rewritten from the files present.

## Art

The generated source images were not kept. The shipped WebP and JPEG files under
`game/client/public/assets/` are the masters; `ui/contract_large.webp` is 1600 px wide, the rest are sized
for the 1280x720 stage.
