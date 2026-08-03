# Archive import change

The service imports customer-provided ZIP archives into an isolated staging
directory. Archive names and member names are untrusted. Existing deployments
run the worker with permission to write anywhere below the application's data
directory.

Review the proposed implementation in `services/` together with its tests.
Prefer a small compatible fix and concrete regression coverage.
