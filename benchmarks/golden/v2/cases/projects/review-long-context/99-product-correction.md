# Final product correction — authoritative

This note supersedes the provisional statement in `00-requirements.md`.

The required precedence is:

1. defaults;
2. project file;
3. environment variables;
4. explicit CLI flags.

The loader must never write the effective configuration back to the project
file. A read-only project file is a supported deployment. The final review
must use this corrected order and call out any proposal based on the earlier
assumption.
