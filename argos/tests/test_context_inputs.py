from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "context_inputs.py"
SPEC = importlib.util.spec_from_file_location("context_inputs_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
context_inputs = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context_inputs
SPEC.loader.exec_module(context_inputs)


class ContextExpansionTests(unittest.TestCase):
    def test_directory_expansion_is_sorted_and_deduplicates_explicit_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zed = root / "zed.txt"
            alpha = root / "Alpha.txt"
            nested = root / "nested"
            nested.mkdir()
            beta = nested / "beta.txt"
            for path, text in ((zed, "z"), (alpha, "a"), (beta, "b")):
                path.write_text(text, encoding="utf-8")

            result = context_inputs.expand_context_inputs(
                files=[zed],
                directories=[root],
                max_total_chars=10,
            )

            expected = sorted(
                (alpha.resolve(), beta.resolve(), zed.resolve()),
                key=lambda path: os.path.normcase(str(path)),
            )
            self.assertEqual(list(result.paths), expected)
            self.assertEqual(result.report.total_chars, 3)
            self.assertEqual(len(result.report.included), 3)
            duplicates = [
                item for item in result.report.skipped if item.reason == "duplicate"
            ]
            self.assertEqual(len(duplicates), 1)
            self.assertEqual(duplicates[0].relative_path, "zed.txt")

    def test_include_and_exclude_patterns_use_posix_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pkg").mkdir()
            (root / "pkg" / "keep.py").write_text("keep", encoding="utf-8")
            (root / "pkg" / "generated.py").write_text("generated", encoding="utf-8")
            (root / "root.py").write_text("root", encoding="utf-8")
            (root / "notes.txt").write_text("notes", encoding="utf-8")

            result = context_inputs.expand_context_inputs(
                directories=[root],
                includes=["**/*.py"],
                excludes=["pkg/generated.py"],
            )

            self.assertEqual(
                {path.name for path in result.paths}, {"keep.py", "root.py"}
            )
            reasons = {
                item.relative_path: item.reason for item in result.report.skipped
            }
            self.assertEqual(reasons["notes.txt"], "not_included")
            self.assertEqual(reasons["pkg/generated.py"], "excluded_pattern")

    def test_directory_filters_do_not_override_explicit_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            explicit = root / "review.diff"
            explicit.write_text("diff", encoding="utf-8")
            source = root / "source"
            source.mkdir()
            selected = source / "test_selected.py"
            selected.write_text("selected", encoding="utf-8")

            result = context_inputs.expand_context_inputs(
                files=[explicit],
                directories=[source],
                includes=["test_*.py"],
                excludes=["*.diff"],
            )

            self.assertEqual(
                set(result.paths),
                {explicit.resolve(), selected.resolve()},
            )

    def test_hard_denylist_excludes_caches_secrets_and_binary_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "node_modules"
            cache.mkdir()
            (cache / "package.js").write_text("ignored", encoding="utf-8")
            argos_store = root / ".argos"
            argos_store.mkdir()
            (argos_store / "session.json").write_text("private", encoding="utf-8")
            (root / ".env.production").write_text("TOKEN=secret", encoding="utf-8")
            (root / "private.pem").write_text("secret", encoding="utf-8")
            (root / "cloud-credentials-prod.json").write_text("secret", encoding="utf-8")
            (root / "image.png").write_bytes(b"valid utf8 despite its suffix")
            (root / "safe.txt").write_text("safe", encoding="utf-8")

            result = context_inputs.expand_context_inputs(
                directories=[root],
                includes=["*"],
            )

            self.assertEqual(result.paths, (root.joinpath("safe.txt").resolve(),))
            reasons = {
                (Path(item.path).name, item.reason) for item in result.report.skipped
            }
            self.assertIn(("node_modules", "denied_directory"), reasons)
            self.assertIn((".argos", "denied_directory"), reasons)
            self.assertIn((".env.production", "secret_pattern"), reasons)
            self.assertIn(("private.pem", "secret_pattern"), reasons)
            self.assertIn(("cloud-credentials-prod.json", "secret_pattern"), reasons)
            self.assertIn(("image.png", "binary_extension"), reasons)

    def test_invalid_utf8_nul_binary_and_unreadable_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            invalid = root / "invalid.txt"
            invalid.write_bytes(b"\xff\xfe")
            binary_with_nul = root / "binary-with-nul.txt"
            binary_with_nul.write_bytes(b"before\x00after")

            result = context_inputs.expand_context_inputs(directories=[root])

            reasons = {
                Path(item.path).name: item.reason for item in result.report.skipped
            }
            self.assertEqual(reasons["invalid.txt"], "invalid_utf8")
            self.assertEqual(reasons["binary-with-nul.txt"], "binary_nul")

            readable = root / "readable.txt"
            readable.write_text("text", encoding="utf-8")
            original_open = Path.open

            def failing_open(path: Path, *args: object, **kwargs: object) -> object:
                if path == readable.resolve():
                    raise PermissionError("denied for test")
                return original_open(path, *args, **kwargs)

            with mock.patch.object(
                Path, "open", autospec=True, side_effect=failing_open
            ):
                unreadable_result = context_inputs.expand_context_inputs(
                    files=[readable]
                )
            self.assertEqual(unreadable_result.paths, ())
            self.assertEqual(unreadable_result.report.skipped[0].reason, "unreadable")
            self.assertIn(
                "denied for test", unreadable_result.report.skipped[0].detail or ""
            )

    def test_report_is_json_serializable_and_contains_limits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "file.txt"
            path.write_text("hello", encoding="utf-8")
            result = context_inputs.expand_context_inputs(
                files=[path],
                max_files=2,
                max_file_chars=20,
                max_total_chars=30,
            )

            payload = result.report.to_dict()
            json.dumps(payload)
            self.assertEqual(payload["limits"]["max_files"], 2)
            self.assertEqual(payload["included"][0]["chars"], 5)

    def test_file_character_limit_fails_instead_of_truncating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "large.txt"
            path.write_text("abcdef", encoding="utf-8")
            with self.assertRaisesRegex(
                context_inputs.ContextLimitError, "max_file_chars=5"
            ):
                context_inputs.expand_context_inputs(files=[path], max_file_chars=5)

    def test_total_character_limit_fails_instead_of_truncating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "one.txt").write_text("1234", encoding="utf-8")
            (root / "two.txt").write_text("5678", encoding="utf-8")
            with self.assertRaisesRegex(
                context_inputs.ContextLimitError, "max_total_chars=7"
            ):
                context_inputs.expand_context_inputs(
                    directories=[root], max_total_chars=7
                )

    def test_file_count_limit_fails_instead_of_selecting_a_subset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "one.txt").write_text("1", encoding="utf-8")
            (root / "two.txt").write_text("2", encoding="utf-8")
            with self.assertRaisesRegex(
                context_inputs.ContextLimitError, "max_files=1"
            ):
                context_inputs.expand_context_inputs(directories=[root], max_files=1)

    def test_limits_must_be_positive_integers(self) -> None:
        bad_values = (0, -1, True, 1.5)
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(context_inputs.ContextInputError):
                    context_inputs.expand_context_inputs(max_files=value)

    def test_missing_and_wrong_kind_explicit_inputs_fail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            file_path = root / "file.txt"
            file_path.write_text("text", encoding="utf-8")
            with self.assertRaisesRegex(context_inputs.ContextInputError, "not found"):
                context_inputs.expand_context_inputs(files=[root / "missing.txt"])
            with self.assertRaisesRegex(
                context_inputs.ContextInputError, "not a regular directory"
            ):
                context_inputs.expand_context_inputs(directories=[file_path])

    def test_symlink_outside_root_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            secret = outside / "outside.txt"
            secret.write_text("must not be read", encoding="utf-8")
            link = root / "escape"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest(
                    "directory symlinks are not available for this account/platform"
                )

            result = context_inputs.expand_context_inputs(directories=[root])

            self.assertEqual(result.paths, ())
            self.assertEqual(len(result.report.skipped), 1)
            self.assertEqual(result.report.skipped[0].reason, "symlink_or_reparse")
            self.assertNotIn(secret.resolve(), result.paths)

    def test_explicit_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.txt"
            target.write_text("target", encoding="utf-8")
            link = root / "link.txt"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest(
                    "file symlinks are not available for this account/platform"
                )
            with self.assertRaisesRegex(
                context_inputs.ContextInputError, "symlink or reparse"
            ):
                context_inputs.expand_context_inputs(files=[link])

    def test_windows_reparse_attribute_is_fail_closed(self) -> None:
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        fake_stat = types.SimpleNamespace(st_file_attributes=reparse_flag)
        self.assertTrue(context_inputs._is_reparse_stat(fake_stat))

    def test_duplicate_directory_roots_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "file.txt").write_text("text", encoding="utf-8")
            result = context_inputs.expand_context_inputs(
                directories=[root, root / "."]
            )
            self.assertEqual(len(result.paths), 1)
            self.assertEqual(
                [item.reason for item in result.report.skipped].count("duplicate_root"),
                1,
            )

    @unittest.skipUnless(os.name == "nt", "Windows paths are case-insensitive")
    def test_windows_duplicate_directory_roots_ignore_case(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ArgosCase") as td:
            root = Path(td)
            (root / "file.txt").write_text("text", encoding="utf-8")
            differently_cased = Path(str(root).swapcase())

            result = context_inputs.expand_context_inputs(
                directories=[root, differently_cased]
            )

            self.assertEqual(len(result.paths), 1)
            self.assertEqual(
                [item.reason for item in result.report.skipped].count(
                    "duplicate_root"
                ),
                1,
            )

    def test_explicit_non_secret_file_can_be_selected_from_a_denied_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            hidden = Path(td) / ".omx"
            hidden.mkdir()
            plan = hidden / "plan.md"
            plan.write_text("review this explicit plan", encoding="utf-8")
            result = context_inputs.expand_context_inputs(files=[plan])
            self.assertEqual(result.paths, (plan.resolve(),))

    def test_denied_ancestor_name_does_not_reject_a_safe_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "build" / "project"
            root.mkdir(parents=True)
            safe = root / "safe.txt"
            safe.write_text("safe", encoding="utf-8")

            result = context_inputs.expand_context_inputs(directories=[root])

            self.assertEqual(result.paths, (safe.resolve(),))

    def test_link_swap_detected_immediately_before_read_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "context.txt"
            path.write_text("safe", encoding="utf-8")
            with mock.patch.object(
                context_inputs,
                "_is_link_or_reparse",
                side_effect=[False, True],
            ):
                result = context_inputs.expand_context_inputs(files=[path])

            self.assertEqual(result.paths, ())
            self.assertEqual(
                result.report.skipped[0].reason,
                "symlink_or_reparse",
            )


if __name__ == "__main__":
    unittest.main()
