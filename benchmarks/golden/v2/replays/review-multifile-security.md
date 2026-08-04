## Blockers

- `services/upload.py` passes every archive member to `write_member()` without proving that the resolved destination remains under the safe base directory. An archive path traversal such as `../../outside.txt` therefore escapes the extraction root.
- The same boundary accepts a symlink member. Its target can escape after the lexical path check, so symlink entries must be rejected before any write.

## Important issues

- `tempfile.gettempdir() / upload.filename` derives a temp path from a user-controlled name. A separator or reserved name can redirect or collide with another upload.

## Preferences

- Keep the correction local to archive validation and temp-name generation; a new framework would add no useful protection here.

## Minimal fix plan

1. Resolve each candidate against the fixed base and reject it unless `relative_to(base.resolve())` succeeds.
2. Reject symlink and other link-like archive members before opening the destination.
3. Replace the user-controlled temp name with a generated file and preserve only a validated suffix.
4. Add tests for archive traversal, a symlink escape, and an unsafe upload filename.
