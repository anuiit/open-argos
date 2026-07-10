# Mos-Tools install hardening plan

Date: 2026-07-07

## Goal
Make the `mos-tools` Codex plugin clearer and more reliable to install on POSIX/Linux/WSL, either as a personal/global plugin or repo-local plugin, while keeping prompts structured but lightweight. Native Windows mosaic support is deferred to a dedicated portability pass.

## Fable high implementation order
1. Reconcile installed cache changes back into the source plugin.
2. Bump plugin version to `0.1.1`.
3. Reinstall the plugin cleanly from source.
4. Test `agy` Antigravity vision in non-interactive mode.
5. Migrate `mos-vision` to `agy` where supported, and update `mos-config` only for valid `agy` configuration syntax.
6. Add README and shared mosaic context contract.
7. Smoke test every skill.

## Constraints
- Source of truth: `~/.agents/plugins/plugins/mos-tools`.
- Never hand-edit Codex plugin cache except for inspection/diffing.
- Keep plugin small: docs + skills + optional tiny scripts only.
- Mosaic output is advisory; never execute mosaic suggestions as commands automatically.
- `mosaic` and provider CLIs must exist in the same environment as Codex: Windows native vs WSL matters.

## Acceptance checks
- Plugin manifest validates with `plugin-creator` validator.
- Source version is bumped to `0.1.1`.
- Source and installed cache match after reinstall, or any cache difference is explained as install metadata.
- `mosaic doctor` succeeds.
- `agy` non-interactive capability is tested and result documented.
- Each Mos-Tools skill has a smoke test or an explicit non-destructive skip reason.
