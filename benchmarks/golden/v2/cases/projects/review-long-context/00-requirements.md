# Initial requirements

The configuration loader merges defaults, a project file and explicit CLI
flags. Explicit CLI flags must always win. A missing project file is allowed.
Unknown project keys produce a warning, not a hard failure.

The initial proposal below assumes that environment variables have the
highest precedence. That assumption is provisional and may be corrected by a
later product note.
