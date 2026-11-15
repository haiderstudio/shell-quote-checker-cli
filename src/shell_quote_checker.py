#!/usr/bin/env python3
"""Check shell scripts for unquoted variable expansions.

Run: python3 src/shell_quote_checker.py script.sh
     python3 src/shell_quote_checker.py project/
     python3 src/shell_quote_checker.py --stdin < script.sh

An unquoted $file breaks the moment a filename holds
a space — the shell splits the value into words, and
the command gets two arguments where one was meant.
It is the most common shell scripting bug, and the one
every shell guide warns about first. This tool names
each unquoted expansion — $var, ${var}, $(...), $@,
$* — with the file and the line number, and exits 1
when any is found, so it can fail a CI run. A script
with every expansion quoted exits 0.

It reads shell scripts only. It never edits a file,
never touches the network, and reads only the files
and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

__version__ = "1.0.0"

SHELL_SUFFIX = ".sh"

_ASSIGN_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=")

# Expansions that never split into words, so quoting
# them changes nothing: the argument count, the last
# exit status, the script's own process id, the last
# background job, the option flags, and positional
# parameters $0-$9.
_SINGLE_WORD_SPECIALS = set("#?!-$0123456789")


def _is_name_start(char):
    return char.isalpha() or char == "_"


def _is_name_char(char):
    return char.isalnum() or char == "_"


def _skip_quoted(line, start, quote):
    """Index just past a quoted span starting at start.

    start points at the opening quote. A backslash inside
    a double-quoted span escapes the next character. A
    span with no closing quote runs to the end of the line.
    """
    size = len(line)
    i = start + 1
    while i < size and line[i] != quote:
        if quote == '"' and line[i] == "\\":
            i += 2
        else:
            i += 1
    return i + 1 if i < size else size


def _skip_paren(line, start):
    """Index just past the ")" matching the "(" at start-1.

    start points just after "$(" — depth counts nested
    parentheses, and quoted spans are skipped whole, so
    a ")" inside a string does not close the substitution.
    A substitution with no closing ")" runs to the end of
    the line.
    """
    size = len(line)
    depth = 1
    i = start
    while i < size and depth > 0:
        char = line[i]
        if char == "\\":
            i += 2
            continue
        if char in ("'", '"'):
            i = _skip_quoted(line, i, char)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        i += 1
    return i


def _skip_brace(line, start):
    """Index just past the "}" matching the "${" at start-2.

    start points just after "${" — depth counts nested
    "${...}" pairs, and quoted spans are skipped whole.
    An expansion with no closing "}" runs to the end of
    the line.
    """
    size = len(line)
    depth = 1
    i = start
    while i < size and depth > 0:
        char = line[i]
        if char == "\\":
            i += 2
            continue
        if char in ("'", '"'):
            i = _skip_quoted(line, i, char)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        i += 1
    return i


def _skip_arith(line, start):
    """Index just past the "))" closing a $(( at start-3.

    start points just after "$(( " — depth counts
    parentheses, so a "(a + b)" inside the arithmetic
    does not end it early.
    """
    size = len(line)
    depth = 1
    i = start
    while i < size and depth > 0:
        char = line[i]
        if char == "\\":
            i += 2
            continue
        if char in ("'", '"'):
            i = _skip_quoted(line, i, char)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        i += 1
    return i


def _is_safe_brace_inner(inner):
    """True when a ${...} expansion cannot split words.

    ${#var} is a length and ${#} is a count, ${1} and
    ${10} are positional parameters, and a ${var@...}
    operator returns one quoted or otherwise single
    word. Everything else — ${var}, ${var:-default},
    ${var/foo/bar}, ${!var} — expands to a plain value
    that splits when unquoted.
    """
    if inner == "":
        return True
    if inner.startswith("#"):
        return True
    if inner[0].isdigit():
        return True
    if "@" in inner:
        return True
    return False


def _skip_assignment_rhs(line, start):
    """Index just past one assignment value starting at start.

    The right-hand side of an assignment never splits —
    VAR=$file is safe — so the whole word is skipped.
    An array assignment VAR=(...) is not skipped: the
    values inside the parentheses do split, so scanning
    carries on from the "(" itself. An arithmetic or
    command substitution inside the value is skipped
    whole, so a space inside $((1 + $n)) does not end
    the value early.
    """
    if start < len(line) and line[start] == "(":
        return start
    size = len(line)
    i = start
    while i < size:
        char = line[i]
        if char in " \t;|&":
            break
        if char == "\\":
            i += 2
            continue
        if char in ("'", '"'):
            i = _skip_quoted(line, i, char)
            continue
        if char == "$":
            if line.startswith("$((", i):
                i = _skip_arith(line, i + 3)
                continue
            if line.startswith("$(", i):
                i = _skip_paren(line, i + 2)
                continue
            if line.startswith("${", i):
                i = _skip_brace(line, i + 2)
                continue
        i += 1
    return i


def _scan_line(line, lineno, findings, heredocs):
    """Scan one logical line for unquoted expansions.

    heredocs collects the delimiters of heredocs opened
    on this line, in order, so the lines that follow are
    skipped as heredoc body. A finding is {"line": int,
    "expansion": str, "reason": str}.
    """
    size = len(line)
    i = 0
    while i < size:
        char = line[i]
        if char == "#":
            if i == 0 or line[i - 1] in " \t;|&(":
                break
            i += 1
            continue
        if char == "\\":
            i += 2
            continue
        if char in ("'", '"', "`"):
            i = _skip_quoted(line, i, char)
            continue
        if char == "$":
            if line.startswith("$((", i):
                i = _skip_arith(line, i + 3)
                continue
            if line.startswith("$(", i):
                end = _skip_paren(line, i + 2)
                findings.append({
                    "line": lineno,
                    "expansion": line[i:end],
                    "reason": ("unquoted command substitution — "
                               "quote it or store it in a variable "
                               "first"),
                })
                i = end
                continue
            if line.startswith("${", i):
                end = _skip_brace(line, i + 2)
                inner = line[i + 2:end - 1] if end > i + 2 \
                    and line[end - 1] == "}" else line[i + 2:end]
                if not _is_safe_brace_inner(inner):
                    findings.append({
                        "line": lineno,
                        "expansion": line[i:end],
                        "reason": ("unquoted expansion — quote it so "
                                   "a value with spaces stays one word"),
                    })
                i = end
                continue
            if i + 1 < size and line[i + 1] == "'":
                i = _skip_quoted(line, i + 1, "'")
                continue
            if i + 1 < size and line[i + 1] in "@*":
                findings.append({
                    "line": lineno,
                    "expansion": line[i:i + 2],
                    "reason": ("unquoted %s — quote it so each "
                               "argument stays separate"
                               % line[i:i + 2]),
                })
                i += 2
                continue
            if i + 1 < size and line[i + 1] in _SINGLE_WORD_SPECIALS:
                i += 2
                continue
            if i + 1 < size and _is_name_start(line[i + 1]):
                end = i + 1
                while end < size and _is_name_char(line[end]):
                    end += 1
                findings.append({
                    "line": lineno,
                    "expansion": line[i:end],
                    "reason": ("unquoted variable — quote it so a "
                               "value with spaces stays one word"),
                })
                i = end
                continue
            i += 1
            continue
        if line.startswith("<<<", i):
            break
        if line.startswith("<<", i):
            j = i + 2
            dash = False
            if j < size and line[j] == "-":
                dash = True
                j += 1
            while j < size and line[j] in " \t":
                j += 1
            if j < size and line[j] in ("'", '"'):
                quote = line[j]
                end = line.find(quote, j + 1)
                delim = line[j + 1:end] if end != -1 else ""
                j = end + 1 if end != -1 else size
            else:
                end = j
                while end < size and _is_name_char(line[end]):
                    end += 1
                delim = line[j:end]
                j = end
            if delim:
                heredocs.append((delim, dash))
            i = j
            continue
        if line.startswith("[[", i):
            end = line.find("]]", i + 2)
            i = size if end == -1 else end + 2
            continue
        if line.startswith("((", i):
            end = line.find("))", i + 2)
            i = size if end == -1 else end + 2
            continue
        if _is_name_start(char):
            end = i
            while end < size and _is_name_char(line[end]):
                end += 1
            word = line[i:end]
            if word in ("case", "select"):
                j = end
                while j < size and line[j] in " \t":
                    j += 1
                while j < size and line[j] not in " \t;|&":
                    j += 1
                i = j
                continue
            if word in ("export", "local", "declare", "readonly",
                        "typeset"):
                j = end
                while True:
                    while j < size and line[j] in " \t":
                        j += 1
                    if (j < size and line[j] == "-"
                            and j + 1 < size
                            and line[j + 1].isalpha()):
                        while j < size and line[j] not in " \t":
                            j += 1
                        continue
                    break
                match = _ASSIGN_RE.match(line, j)
                if match:
                    i = _skip_assignment_rhs(line, match.end())
                    continue
                i = end
                continue
            match = _ASSIGN_RE.match(line, i)
            if match:
                i = _skip_assignment_rhs(line, match.end())
                continue
            i = end
            continue
        i += 1


def _ends_with_continuation(line):
    """True when a line ends in an odd run of backslashes."""
    count = 0
    j = len(line) - 1
    while j >= 0 and line[j] == "\\":
        count += 1
        j -= 1
    return count % 2 == 1


def check_text(text):
    """Check one document's text.

    Returns a list of findings, each {"line": int,
    "expansion": str, "reason": str}, in document order.
    Full-line comments, single-quoted strings,
    double-quoted strings, heredoc bodies, and line
    continuations are handled; a finding reports the
    first line of a continued line.
    """
    findings = []
    heredocs = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if heredocs:
            delim, dash = heredocs[0]
            body = lines[i].strip() if dash else lines[i]
            if body == delim:
                heredocs.pop(0)
            i += 1
            continue
        lineno = i + 1
        logical = lines[i]
        i += 1
        while (_ends_with_continuation(logical)
               and i < len(lines)):
            logical = logical[:-1] + " " + lines[i]
            i += 1
        _scan_line(logical, lineno, findings, heredocs)
    findings.sort(key=lambda item: item["line"])
    return findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    return check_text(text), None


def _is_shell_file(path):
    """True for .sh files and extensionless shell scripts.

    An extensionless file counts when its first line is a
    shell shebang. A file that cannot be read is not a
    shell file.
    """
    if path.name.endswith(SHELL_SUFFIX):
        return True
    if "." in path.name:
        return False
    try:
        with open(path, "r", encoding="utf-8",
                  errors="strict") as handle:
            first = handle.readline()
    except (OSError, UnicodeDecodeError):
        return False
    return first.startswith("#!") and ("sh" in first or "bash" in first)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of shell files.

    A file given directly is always checked, whatever its
    name. A folder is walked for shell files only — .sh
    files and extensionless files with a shell shebang.
    .git folders are never walked, and directory links
    are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_shell_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one unquoted expansion."""
    return ("FAIL %s: %s line %d %s"
            % (path, finding["expansion"], finding["line"],
               finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no shell files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d unquoted expansion(s) in "
                  "%d file(s)." % (len(files), findings,
                                   files_with_findings))
        else:
            print("OK — %d file(s) checked, every expansion quoted."
                  % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one shell document read from standard input."""
    text = sys.stdin.read()
    bad = check_text(text)
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d unquoted expansion(s) in "
                  "1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every expansion quoted.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="shell_quote_checker",
        description="Check shell scripts for unquoted variable "
                    "expansions, fail CI when one is found. "
                    "Report-only — it never edits a file.")
    parser.add_argument("paths", nargs="*",
                        help="shell files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one shell document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one shell file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
