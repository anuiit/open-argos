diff --git a/scripts/bench_argos_quality.py b/scripts/bench_argos_quality.py
@@
-ARGOS_DEV = ROOT / "bin/argos-dev"
+ARGOS_DEV = ROOT / "bin/argos-dev.cmd"

The old path works in Bash-like shells but is fragile on Windows when invoked
through PowerShell. The fix should keep the launcher deterministic and
cross-platform.
