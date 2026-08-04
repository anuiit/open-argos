# Options under consideration

## Incremental standard-library runner

Use `argparse`, dataclasses, `subprocess`, JSON and small execution adapters.
It reuses the existing entrypoint and has a narrow migration.

## Workflow framework

Adopt a general DAG framework with plugins, persistent workers and its own
configuration language. It offers retries and visualization, but adds a
runtime service, packaging work and a second state model.

The decision should be revisited if the workload later requires distributed
scheduling or durable remote workers.
