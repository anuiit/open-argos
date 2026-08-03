# Migration notes

Existing automation passes `--timeout 30` to override a project default of
120 seconds. Some installations also export `APP_TIMEOUT=90`. The migration
must keep automation deterministic across Windows and Linux.

The project file is checked into source control. It is not a cache and should
not receive values derived from one developer's environment. A dry run must
remain read-only.

The implementation team plans to add a focused precedence table test. No
framework migration is in scope.
