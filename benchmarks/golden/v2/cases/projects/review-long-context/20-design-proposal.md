# Design proposal

The proposed merge order is:

1. defaults;
2. CLI flags;
3. project file;
4. environment variables.

The implementation writes the merged mapping back to the project file after a
successful run so subsequent commands see the same values. Reviewers should
consider compatibility, observability and whether persisted state can change
the meaning of a later invocation.

Several teams still invoke the CLI from read-only worktrees. The author argues
that a write-back failure can be ignored because the in-memory run completed.
