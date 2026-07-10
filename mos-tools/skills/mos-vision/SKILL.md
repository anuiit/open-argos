---
name: mos-vision
description: Analyze local images through mosaic's Antigravity `agy` image route when the user asks for image/screenshot critique via mosaic. Requires image paths and uses `mosaic @vision --image`.
---

Use mosaic's Antigravity-backed image route.

Before running mosaic, follow `../../references/mosaic-context-contract.md`.

Steps:
1. Identify local image paths. Supported MIME types are PNG, JPEG, WEBP, HEIC, and HEIF.
2. Prefer `mosaic @vision "<question>" --image <path>` with repeated `--image` for multiple images; this routes to `agy_image` by default.
3. If `agy` or credentials are unavailable, report the capability blocker / `needs_human` and use Codex-native visual inspection only if appropriate. Do not fall back to another vision provider; Antigravity `agy` is the only supported mosaic vision route.
4. Report command, artifact path, and key visual findings.
