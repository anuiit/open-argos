The stdlib runner and the proposed framework solve different scales of problem.
The current constraints require offline execution, deterministic artifacts, and
no new dependency; stdlib therefore fits the present CLI better. The framework
would add plugin ergonomics, but also installation, migration, and operational
cost without evidence that the current concurrency is insufficient.

Recommendation:

1. Keep the stdlib implementation and isolate adapters behind the existing
   command-runner boundary.
2. Add a benchmark test for each launch surface and a phased verification run.
3. Defer the framework until a measured concurrency or extension constraint
   becomes a trigger; record that trigger so the choice is reversible.
4. If the trigger is reached, run a small migration pilot with rollback rather
   than replacing the harness in one step.
