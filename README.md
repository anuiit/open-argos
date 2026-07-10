# mosaic-dev

Isolated benchmark-driven working copy for the local `mosaic` CLI and `mos-tools` plugin facade.

- Stable mosaic remains `/home/sina/.local/bin/mosaic -> /home/sina/.config/mosaic/mosaic.py`.
- Dev CLI entrypoint: `./bin/mosaic-dev`.
- Dev config: `.config/mosaic-dev/config.json`.
- Dev artifacts: `.mosaic/sessions/`.
- Dev locks: `.mosaic/locks/`.

Do not promote changes to the stable mosaic/plugin without explicit human validation.
