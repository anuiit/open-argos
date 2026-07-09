# advisor-dev

Isolated benchmark-driven working copy for the local `advisor` CLI and `adv-tools` plugin facade.

- Stable advisor remains `/home/sina/.local/bin/advisor -> /home/sina/.config/advisor/advisor.py`.
- Dev CLI entrypoint: `./bin/advisor-dev`.
- Dev config: `.config/advisor-dev/config.json`.
- Dev artifacts: `.advisor/sessions/`.
- Dev locks: `.advisor/locks/`.

Do not promote changes to the stable advisor/plugin without explicit human validation.
