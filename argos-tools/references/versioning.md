# Argos Tools versioning and update story

`argos-tools` has two related but different versions:

1. **Source/release version**: the SemVer prefix in `.codex-plugin/plugin.json`, for example `0.1.2`.
2. **Local Codex cachebuster**: a `+codex.<timestamp>` suffix added during local reinstall, for example `0.1.2+codex.20260707193000`.

Rules:

- Bump the SemVer prefix only when the plugin behavior/docs/skills change.
- Use `plugin-creator/scripts/update_plugin_cachebuster.py` to refresh the suffix while iterating locally.
- Do not edit Codex installed cache directories; edit `~/plugins/argos-tools` and reinstall.
- Keep argos CLI compatibility explicit in README and `$argos-doctor`.
- After reinstall, use a new Codex thread to pick up changed skills/tools.

Recommended update loop:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ~/plugins/argos-tools
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py ~/plugins/argos-tools
MARKETPLACE=$(python3 ~/.codex/skills/.system/plugin-creator/scripts/read_marketplace_name.py)
codex plugin add argos-tools@$MARKETPLACE
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py
```

Windows notes:

- Experimental native Windows shims depend on `argos >= 0.6.0`; real native Windows validation is still required before calling it fully supported.
- WSL remains the most predictable install surface when provider CLIs differ between Windows and Linux.
- A repo-local marketplace on Windows should use the same Codex marketplace JSON shape; paths are normal Windows paths when run from native Windows, and `/mnt/<drive>/...` when run from WSL.
