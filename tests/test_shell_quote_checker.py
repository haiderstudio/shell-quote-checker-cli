#!/usr/bin/env python3
"""Tests for shell_quote_checker — stdlib unittest only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import shell_quote_checker as checker

REPO = Path(__file__).resolve().parent.parent


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def expansions_of(text):
    return checker.check_text(text)


class TestFlagged(unittest.TestCase):
    def test_plain_variable_flagged(self):
        bad = expansions_of("echo $file\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(bad[0]["expansion"], "$file")

    def test_braced_variable_flagged(self):
        bad = expansions_of("echo ${file}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "${file}")

    def test_braced_with_default_flagged(self):
        bad = expansions_of("echo ${file:-none}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "${file:-none}")

    def test_command_substitution_flagged_once(self):
        bad = expansions_of("echo $(ls $file)\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$(ls $file)")

    def test_at_flagged(self):
        bad = expansions_of("for arg in $@; do echo $arg; done\n")
        self.assertEqual([item["expansion"] for item in bad],
                         ["$@", "$arg"])

    def test_star_flagged(self):
        bad = expansions_of("echo $*\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$*")

    def test_mid_word_variable_flagged(self):
        bad = expansions_of("cp prefix$file.txt dest/\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$file")

    def test_two_on_one_line(self):
        bad = expansions_of("cp $src $dest\n")
        self.assertEqual([item["expansion"] for item in bad],
                         ["$src", "$dest"])

    def test_indirect_expansion_flagged(self):
        bad = expansions_of("echo ${!name}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "${!name}")

    def test_findings_in_line_order(self):
        bad = expansions_of("echo $b\necho $a\n")
        self.assertEqual([item["line"] for item in bad], [1, 2])


class TestSafe(unittest.TestCase):
    def test_double_quoted_passes(self):
        self.assertEqual(expansions_of('echo "$file"\n'), [])

    def test_single_quoted_passes(self):
        self.assertEqual(expansions_of("echo '$file'\n"), [])

    def test_full_line_comment_passes(self):
        self.assertEqual(expansions_of("# echo $file\n"), [])

    def test_trailing_comment_passes(self):
        self.assertEqual(expansions_of("echo hi # $file\n"), [])

    def test_hash_in_word_not_a_comment(self):
        bad = expansions_of("echo file#1 $file\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$file")

    def test_escaped_dollar_passes(self):
        self.assertEqual(expansions_of("echo \\$file\n"), [])

    def test_assignment_rhs_passes(self):
        self.assertEqual(expansions_of("dest=$file.bak\n"), [])

    def test_export_assignment_passes(self):
        self.assertEqual(expansions_of("export DEST=$file\n"), [])

    def test_local_assignment_passes(self):
        self.assertEqual(expansions_of("local dest=$file\n"), [])

    def test_declare_with_flag_passes(self):
        self.assertEqual(expansions_of("declare -r DEST=$file\n"), [])

    def test_append_assignment_passes(self):
        self.assertEqual(expansions_of("PATH=$PATH:/bin\n"), [])

    def test_assignment_then_arg_flagged(self):
        bad = expansions_of("dest=$file echo $other\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$other")

    def test_array_assignment_contents_flagged(self):
        bad = expansions_of("arr=($one $two)\n")
        self.assertEqual([item["expansion"] for item in bad],
                         ["$one", "$two"])

    def test_double_bracket_test_passes(self):
        self.assertEqual(expansions_of("if [[ -n $file ]]; then\n"), [])

    def test_single_bracket_test_flagged(self):
        bad = expansions_of("if [ -n $file ]; then\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$file")

    def test_arithmetic_passes(self):
        self.assertEqual(expansions_of("count=$((1 + $n))\n"), [])

    def test_arithmetic_command_passes(self):
        self.assertEqual(expansions_of("(( total += $n ))\n"), [])

    def test_case_subject_passes(self):
        self.assertEqual(expansions_of("case $file in\n"), [])

    def test_case_body_flagged(self):
        bad = expansions_of("case $file in\n  *.txt) echo $hit ;;\nesac\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$hit")

    def test_positional_passes(self):
        self.assertEqual(expansions_of("echo $1 $2 $9\n"), [])

    def test_braced_positional_passes(self):
        self.assertEqual(expansions_of("echo ${10}\n"), [])

    def test_length_expansion_passes(self):
        self.assertEqual(expansions_of("echo ${#file}\n"), [])

    def test_count_passes(self):
        self.assertEqual(expansions_of("echo $# $?\n"), [])

    def test_pid_and_job_passes(self):
        self.assertEqual(expansions_of("echo $$ $! $-\n"), [])

    def test_quoted_at_passes(self):
        self.assertEqual(expansions_of('for arg in "$@"; do echo "$arg"; done\n'),
                         [])

    def test_heredoc_body_passes(self):
        bad = expansions_of("cat <<EOF\nThe file is $file\nEOF\n")
        self.assertEqual(bad, [])

    def test_quoted_heredoc_passes(self):
        bad = expansions_of("cat <<'EOF'\nThe file is $file\nEOF\n")
        self.assertEqual(bad, [])

    def test_dash_heredoc_indented_close(self):
        bad = expansions_of("cat <<-EOF\n\tThe file is $file\n\tEOF\n")
        self.assertEqual(bad, [])

    def test_two_heredocs_in_order(self):
        bad = expansions_of(
            "cat <<A <<B\n$a\nA\n$b\nB\necho $after\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expansion"], "$after")

    def test_herestring_passes(self):
        self.assertEqual(expansions_of("grep error <<< $file\n"), [])

    def test_ansi_c_quoting_passes(self):
        self.assertEqual(expansions_of("echo $'a $file b'\n"), [])

    def test_continued_line_reports_first_line(self):
        bad = expansions_of("echo \\\n  $file\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)

    def test_empty_document_passes(self):
        self.assertEqual(expansions_of(""), [])

    def test_backtick_span_skipped(self):
        self.assertEqual(expansions_of("echo `echo $file`\n"), [])

    def test_quoted_substitution_passes(self):
        self.assertEqual(expansions_of('listing="$(ls "$file")"\n'), [])


class TestCli(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ok.sh", 'echo "$file"\n')
            code, out, _ = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK", out)
            self.assertIn("every expansion quoted", out)

    def test_flagged_file_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.sh", "echo $file\n")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("FAIL %s: $file line 1" % path, out)
            self.assertIn("1 unquoted expansion(s)", out)

    def test_folder_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", 'echo "$file"\n')
            write(tmp, "b.sh", "echo $file\n")
            write(tmp, "notes.txt", "echo $file\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertNotIn("notes.txt", out)

    def test_extensionless_shebang_script_walked(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "run", "#!/bin/sh\necho $file\n")
            write(tmp, "plain", "echo $file\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)
            self.assertIn("run", out)
            self.assertNotIn("plain", out)

    def test_nested_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "sub/deep.sh", "echo $file\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("deep.sh", out)

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "top.sh", 'echo "$file"\n')
            write(tmp, "sub/deep.sh", "echo $file\n")
            code, out, _ = run_cli(["--no-recursive", tmp])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.sh", "echo $file\n")
            write(tmp, "skip.sh", "echo $other\n")
            code, out, _ = run_cli(["--exclude", "skip.sh", tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)
            self.assertNotIn("skip.sh", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".git/hooks/bad.sh", "echo $file\n")
            write(tmp, "a.sh", 'echo "$file"\n')
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "script.txt", "echo $file\n")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("script.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.sh", "echo $file\n")
            code, out, _ = run_cli([path, path])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.sh", "echo $file\n")
            code, out, _ = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["findings"][0]["expansion"],
                             "$file")
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO('echo "$file"\n')
        try:
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("every expansion quoted", out)

    def test_stdin_dirty(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("echo $file\n")
        try:
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>: $file line 1", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _, err = run_cli(["--stdin", "a.sh"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, _, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, _, err = run_cli(["/no/such/file.sh"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no shell files found", err)

    def test_bad_flag_exit_2(self):
        code, _, _ = run_cli(["--nope", "a.sh"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("shell_quote_checker", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.sh", b"\xff\xfe")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = "echo $file\n"
            path = write(tmp, "bad.sh", text)
            run_cli([path])
            self.assertEqual(Path(path).read_text(), text)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.sh", "echo $file\n")
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src" / "shell_quote_checker.py"), path],
                capture_output=True, text=True, cwd="/")
            self.assertEqual(result.returncode, 1)
            self.assertIn("$file line 1", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.sh", "echo $file\n")
            env = dict(os.environ, HOME=tmp)
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src" / "shell_quote_checker.py"), path],
                capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual(result.returncode, 1)

    def test_run_example_output_matches_sample(self):
        sample = (REPO / "examples" / "sample-output.md").read_text()
        result = subprocess.run(
            ["sh", str(REPO / "examples" / "run-example.sh")],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), sample.strip())

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        flagged = (REPO / "examples" / "flagged.sh").read_text()
        bad = checker.check_text(flagged)
        for item in bad:
            line = ("FAIL examples/flagged.sh: %s line %d %s"
                    % (item["expansion"], item["line"], item["reason"]))
            self.assertIn(line, readme)


class TestExamples(unittest.TestCase):
    def test_clean_example_passes(self):
        code, _, _ = run_cli([str(REPO / "examples" / "clean.sh")])
        self.assertEqual(code, 0)

    def test_flagged_example_fails_with_six(self):
        bad = checker.check_text(
            (REPO / "examples" / "flagged.sh").read_text())
        self.assertEqual(len(bad), 6)
        self.assertEqual(
            [item["expansion"] for item in bad],
            ["$file", "$file", "${file}", "$(ls $file)", "$@", "$arg"])

    def test_edge_example_passes(self):
        code, _, _ = run_cli([str(REPO / "examples" / "edge.sh")])
        self.assertEqual(code, 0)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True):
        """Every file in the repo, minus .git and caches."""
        for path in REPO.rglob("*"):
            if path.is_dir():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            if skip_tests and "tests" in path.parts:
                continue
            yield path

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        import ast
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src" / "shell_quote_checker.py",
                       REPO / "tests" / "test_shell_quote_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"shell_quote_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src" / "shell_quote_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertTrue(lines, ".gitignore is empty")
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("tests/test_shell_quote_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_shellcheck_and_neighbour(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("ShellCheck", readme)
        self.assertIn("shell-shebang-checker-cli", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
