"""Tests for json_required_key_checker.

Run from the repo root:

    python3 tests/test_json_required_key_checker.py
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "json_required_key_checker.py"

sys.path.insert(0, str(REPO / "src"))
import json_required_key_checker as tool  # noqa: E402


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return str(path)


def run_cli(args, input=None, cwd=None):
    result = subprocess.run(
        [sys.executable, str(SRC)] + args,
        cwd=cwd or str(REPO), capture_output=True, text=True,
        input=input)
    return result.returncode, result.stdout, result.stderr


REQ = ["--require", "name", "--require", "version"]


class TestCheckText(unittest.TestCase):
    def test_all_present_passes(self):
        bad, error = tool.check_text(
            '{"name": "a", "version": "1"}\n', ["name", "version"])
        self.assertEqual((bad, error), ([], None))

    def test_missing_top_level_key_reports_line_one(self):
        bad, error = tool.check_text(
            '{\n  "name": "a"\n}\n', ["name", "version"])
        self.assertIsNone(error)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertIn('"version"', bad[0]["reason"])

    def test_missing_nested_key_reports_parent_line(self):
        bad, error = tool.check_text(
            '{\n  "author": {\n    "name": "Ada"\n  },\n'
            '  "name": "a"\n}\n',
            ["author.email"])
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)
        self.assertIn('"author.email"', bad[0]["reason"])

    def test_nested_key_present_passes(self):
        bad, error = tool.check_text(
            '{"author": {"email": "a@b.c", "name": "Ada"}, '
            '"name": "a"}\n',
            ["author.email", "author.name"])
        self.assertEqual((bad, error), ([], None))

    def test_deeply_nested_missing_key(self):
        bad, error = tool.check_text(
            '{\n  "a": {\n    "b": {\n      "c": 1\n    }\n  }\n}\n',
            ["a.b.d"])
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 3)
        self.assertIn('"a.b.d"', bad[0]["reason"])

    def test_parent_not_an_object(self):
        bad, error = tool.check_text(
            '{"author": "Ada"}\n', ["author.email"])
        self.assertEqual(len(bad), 1)
        self.assertIn("not an object", bad[0]["reason"])

    def test_empty_object_reports_missing_key(self):
        bad, error = tool.check_text(
            '{"author": {}}\n', ["author.email"])
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertIn('"author.email" is missing', bad[0]["reason"])
        self.assertNotIn("not an object", bad[0]["reason"])

    def test_null_value_counts_as_present(self):
        bad, error = tool.check_text(
            '{"name": null}\n', ["name"])
        self.assertEqual((bad, error), ([], None))

    def test_false_and_zero_count_as_present(self):
        bad, error = tool.check_text(
            '{"enabled": false, "count": 0}\n', ["enabled", "count"])
        self.assertEqual((bad, error), ([], None))

    def test_document_array_reports_root_not_object(self):
        bad, error = tool.check_text(
            '[{"name": "a"}]\n', ["name"])
        self.assertEqual(len(bad), 1)
        self.assertIn("not an object", bad[0]["reason"])

    def test_objects_inside_arrays_not_checked(self):
        bad, error = tool.check_text(
            '{"items": [{"name": "one"}]}\n', ["name"])
        self.assertEqual(len(bad), 1)
        self.assertIn('"name" is missing', bad[0]["reason"])

    def test_invalid_json_is_an_error(self):
        bad, error = tool.check_text('{"name": 1,\n', ["name"])
        self.assertEqual(bad, [])
        self.assertIn("not valid JSON", error)

    def test_colon_inside_string_value_not_a_key(self):
        bad, error = tool.check_text(
            '{\n  "meta": {\n    "note": "see: this",\n'
            '    "owner": "Z"\n  },\n  "name": "a"\n}\n',
            ["meta.owner"])
        self.assertEqual((bad, error), ([], None))

    def test_findings_follow_require_order(self):
        bad, error = tool.check_text('{}\n', ["version", "name"])
        self.assertEqual([f["reason"] for f in bad],
                         ['key "version" is missing',
                          'key "name" is missing'])

    def test_duplicate_keys_first_wins(self):
        bad, error = tool.check_text(
            '{"name": "a", "name": "b"}\n', ["name"])
        self.assertEqual((bad, error), ([], None))


class TestCli(unittest.TestCase):
    def test_clean_file_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            code, out, err = run_cli(REQ + [path])
            self.assertEqual(code, 0)
            self.assertIn("every required key is present", out)

    def test_flagged_file_exits_one_with_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{\n  "name": "a"\n}\n')
            code, out, err = run_cli(REQ + [path])
            self.assertEqual(code, 1)
            self.assertIn('line 1 key "version" is missing', out)
            self.assertIn("Checked 1 file(s), 1 required key(s)", out)

    def test_folder_walks_json_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            write(tmp, "b.json", '{"name": "a"}\n')
            write(tmp, "notes.txt", '{"name": "a"}\n')
            code, out, err = run_cli(REQ + [tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s), 1 required key(s)", out)

    def test_no_recursive_stops_at_top_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            write(tmp, "sub/b.json", '{"name": "a"}\n')
            code, out, err = run_cli(
                REQ + ["--no-recursive", tmp])
            self.assertEqual(code, 0)
            code, out, err = run_cli(REQ + [tmp])
            self.assertEqual(code, 1)

    def test_exclude_skips_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            write(tmp, "b.json", '{"name": "a"}\n')
            code, out, err = run_cli(
                REQ + ["--exclude", "b.json", tmp])
            self.assertEqual(code, 0)

    def test_git_folder_never_walked(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            write(tmp, ".git/b.json", '{"name": "a"}\n')
            code, out, err = run_cli(REQ + [tmp])
            self.assertEqual(code, 0)

    def test_file_given_directly_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "data.txt", '{"name": "a"}\n')
            code, out, err = run_cli(REQ + [path])
            self.assertEqual(code, 1)

    def test_missing_path_is_usage_error(self):
        code, out, err = run_cli(REQ + ["no-such-file.json"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_missing_require_flag_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"name": "a"}\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 2)

    def test_invalid_json_file_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"name": 1,\n')
            code, out, err = run_cli(REQ + [path])
            self.assertEqual(code, 1)
            self.assertIn("not valid JSON", out)

    def test_invalid_utf8_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            path.write_bytes(b'{"name": "\xff"}\n')
            code, out, err = run_cli(REQ + [str(path)])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{\n  "name": "a"\n}\n')
            code, out, err = run_cli(REQ + ["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["findings"][0]["line"], 1)

    def test_stdin_clean(self):
        code, out, err = run_cli(
            REQ + ["--stdin"],
            input='{"name": "a", "version": "1"}\n')
        self.assertEqual(code, 0)
        self.assertIn("every required key is present", out)

    def test_stdin_flagged(self):
        code, out, err = run_cli(
            REQ + ["--stdin"],
            input='{\n  "name": "a"\n}\n')
        self.assertEqual(code, 1)
        self.assertIn('FAIL <stdin>: line 1 key "version" is missing', out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"name": "a"}\n')
            before = Path(path).read_text()
            run_cli(REQ + [path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            result = subprocess.run(
                [sys.executable, str(SRC)] + REQ + ["a.json"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every required key is present", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"name": "a", "version": "1"}\n')
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli(REQ + [path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        full = ["--require", "name", "--require", "version",
                "--require", "author.name", "--require", "author.email"]
        clean = subprocess.run(
            [sys.executable, "src/json_required_key_checker.py"]
            + full + ["examples/clean.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/json_required_key_checker.py"]
            + full + ["examples/flagged.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/json_required_key_checker.py"]
            + REQ + ["examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 1 required key(s) missing "
                      "in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 1 required key(s) missing "
                      "in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/json_required_key_checker.py",
             "--require", "name", "--require", "version",
             "--require", "meta.owner", "examples/edge.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/json_required_key_checker.py"]
            + full + ["--json", "examples/flagged.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/json_required_key_checker.py",
                       REPO / "tests/test_json_required_key_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"json_required_key_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/json_required_key_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_json_required_key_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("json-formatter-validator-cli", readme)
        self.assertIn("json-duplicate-key-checker-cli", readme)
        self.assertIn("json-key-sort-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
