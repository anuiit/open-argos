# Runner constraints

- Python 3.11+ and standard library only.
- One executable CLI on Windows and Linux.
- Expected workload: at most 300 launch specifications per run.
- Results are local JSON and Markdown files.
- Existing tests patch the subprocess adapter directly.
- A new dependency needs a measurable capability the standard library cannot
  provide.
