# shell-quote-checker-cli

Check shell scripts for unquoted variable expansions, fail CI when one is found.

[![CI](https://github.com/haiderstudio/shell-quote-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/shell-quote-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`shell_quote_checker` reads shell scripts, checks
every variable expansion, and reports each one used
bare where word-splitting can bite — `$var`,
`${var}`, `$(...)`, `$@`, `$*` — with the file and
the line number. It exits 1 when any unquoted
expansion is found, so it can fail a CI run. A script
with every expansion quoted exits 0.

- An unquoted `$file` breaks the moment a filename
  holds a space: the shell splits the value into
  words, and the command gets two arguments where one
  was meant. It is the most common shell scripting
  bug, and the one every shell guide warns about
  first. A gate that names the exact line is worth
  more than the warning.
- A quoted expansion is never flagged: `"$file"`,
  `'literal'`, and `\$file` are all safe, and so is
  an expansion inside a double-quoted string or a
  backtick span.
- Some unquoted spots cannot split, and they are
  never flagged: the right-hand side of an assignment
  (`dest=$file`), inside `[[ ... ]]`, inside `$(( ... ))`
  and `(( ... ))`, the subject of a `case` or `select`,
  a herestring (`grep error <<< $file`), and
  single-word values (`$#`, `$?`, `$$`, `$!`, `$-`,
  `$1`–`$9`, `${10}`, `${#file}`).
- Comments are never checked, and neither is a
  heredoc body — a `$file` inside a `<<EOF` block is
  skipped, however the heredoc is quoted, and a
  `<<-` heredoc may close with an indented delimiter.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  shell files only — `.sh` files, and extensionless
  files with a shell shebang — recursively by default
  (`--no-recursive` stops at the top level). `.git`
  folders are never walked, and directory links are
  never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one shell document read from standard input.
- A line continued with a backslash is checked as one
  line, and a finding on it reports the first line.

## Who it is for

Anyone who writes or reviews shell scripts — which is
every developer with a deploy script, a build script,
or a cron job. One unquoted variable is the difference
between a script that works and a script that works
until the first filename with a space in it. This is
the gate that names the exact line at the pull
request.

## What it does NOT do

- It does not lint a whole shell script. That is
  [ShellCheck](https://github.com/koalaman/shellcheck)
  (40,337 stars, checked Nov 14, 2026), a whole
  static-analysis tool for shell scripts — quoting is
  one check among hundreds there, and it needs
  installing. This repo is one check only, as a
  zero-install standard-library CLI with per-line
  reporting and a CI exit code. Whole-script linting
  is ShellCheck's job, not this repo's — use it when
  you want the full check.
- It does not check the shebang line. That is repo
  #64, shell-shebang-checker-cli — the shebang is a
  different check on the same files.
- It does not check expansions inside a `$(...)` on
  the same line separately: an unquoted `$(ls $file)`
  is reported once, as the substitution. A
  multi-line substitution's later lines are checked on
  their own.
- It does not fix a script or rewrite a file. It
  reports, you add the quotes.
- It never touches the network, and it only reads the
  files and folders you point it at.

## How this differs

- A fresh search of GitHub on Nov 14, 2026 found 0
  results for `"shell-quote-checker-cli"` and 0
  results for `shell quote checker` — the field is
  completely empty for this job. No rival does the
  one-check quoting gate.
- So the narrow slice stands: unquoted expansions
  only, per-line reporting, a CI exit code, and a
  report-only tool that never edits a file — with
  ShellCheck named honestly above for anyone who
  wants the whole-script check.

## Install

```sh
git clone https://github.com/haiderstudio/shell-quote-checker-cli.git
cd shell-quote-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one script:

```sh
python3 src/shell_quote_checker.py script.sh
```

A script with every expansion quoted passes:

```sh
$ python3 src/shell_quote_checker.py examples/clean.sh
OK — 1 file(s) checked, every expansion quoted.
```

A script with unquoted expansions fails, with the
expansion and line for each one:

```sh
$ python3 src/shell_quote_checker.py examples/flagged.sh
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: ${file} line 6 unquoted expansion — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $(ls $file) line 7 unquoted command substitution — quote it or store it in a variable first
FAIL examples/flagged.sh: $@ line 8 unquoted $@ — quote it so each argument stays separate
FAIL examples/flagged.sh: $arg line 9 unquoted variable — quote it so a value with spaces stays one word
Checked 1 file(s), 6 unquoted expansion(s) in 1 file(s).
```

Check a whole folder (shell files only — the
extensionless `run-example.sh` counts, because it
carries a shell shebang):

```sh
$ python3 src/shell_quote_checker.py examples/
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: ${file} line 6 unquoted expansion — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $(ls $file) line 7 unquoted command substitution — quote it or store it in a variable first
FAIL examples/flagged.sh: $@ line 8 unquoted $@ — quote it so each argument stays separate
FAIL examples/flagged.sh: $arg line 9 unquoted variable — quote it so a value with spaces stays one word
Checked 4 file(s), 6 unquoted expansion(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ python3 src/shell_quote_checker.py --stdin < examples/flagged.sh
FAIL <stdin>: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL <stdin>: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL <stdin>: ${file} line 6 unquoted expansion — quote it so a value with spaces stays one word
FAIL <stdin>: $(ls $file) line 7 unquoted command substitution — quote it or store it in a variable first
FAIL <stdin>: $@ line 8 unquoted $@ — quote it so each argument stays separate
FAIL <stdin>: $arg line 9 unquoted variable — quote it so a value with spaces stays one word
Checked 1 file(s), 6 unquoted expansion(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/shell_quote_checker.py --json examples/flagged.sh
{
  "files": [
    {
      "path": "examples/flagged.sh",
      "findings": [
        {
          "line": 5,
          "expansion": "$file",
          "reason": "unquoted variable — quote it so a value with spaces stays one word"
        },
        {
          "line": 5,
          "expansion": "$file",
          "reason": "unquoted variable — quote it so a value with spaces stays one word"
        },
        {
          "line": 6,
          "expansion": "${file}",
          "reason": "unquoted expansion — quote it so a value with spaces stays one word"
        },
        {
          "line": 7,
          "expansion": "$(ls $file)",
          "reason": "unquoted command substitution — quote it or store it in a variable first"
        },
        {
          "line": 8,
          "expansion": "$@",
          "reason": "unquoted $@ — quote it so each argument stays separate"
        },
        {
          "line": 9,
          "expansion": "$arg",
          "reason": "unquoted variable — quote it so a value with spaces stays one word"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 6
}
```

Exit codes: 0 when every expansion is quoted, 1 when
any unquoted expansion is found or a file cannot be
read, 2 for a usage error (a missing path, a bad flag,
or no shell files found).

## Examples

Tricky cases that are all safe — `examples/edge.sh`
has a single-quoted `$file`, a comment holding one,
an escaped one, `$#` and `$?`, a `case` subject, an
arithmetic block, a heredoc body holding `$file`, a
herestring, and `${10}` with `${#file}` — and it
passes:

```sh
$ python3 src/shell_quote_checker.py examples/edge.sh
OK — 1 file(s) checked, every expansion quoted.
```

An assignment right-hand side is safe, but the same
variable as a command argument is not — the tool
knows the difference:

```sh
$ printf 'dest=$file\ncp $file dest/\n' > /tmp/two.sh
$ python3 src/shell_quote_checker.py /tmp/two.sh
FAIL /tmp/two.sh: $file line 2 unquoted variable — quote it so a value with spaces stays one word
Checked 1 file(s), 1 unquoted expansion(s) in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_shell_quote_checker.py
```

The tests cover flagged expansions (a plain variable,
a braced variable, a braced variable with a default,
a command substitution reported once, `$@` and `$*`,
a mid-word variable, two on one line, an indirect
`${!name}`, findings in line order), safe spots (a
double-quoted variable, a single-quoted variable, a
full-line comment, a trailing comment, a `#` inside a
word, an escaped dollar, an assignment right-hand
side, `export`/`local`/`declare` assignments, an
append assignment, an assignment followed by a flagged
argument, array assignment contents flagged, a
`[[ ... ]]` test, a single-bracket test flagged,
arithmetic, an arithmetic command, a `case` subject,
a `case` body flagged, positional parameters, a
braced positional, a length expansion, `$#` and `$?`,
`$$`/`$!`/`$-`, a quoted `$@`, a heredoc body, a
quoted heredoc, a `<<-` heredoc with an indented
close, two heredocs in order, a herestring, ANSI-C
quoting, a continued line reporting its first line,
backtick spans, a quoted substitution), the CLI (exit
0/1/2, folder walking for several shell files, an
extensionless shebang script walked while a plain text
file is not, nested folders, `--no-recursive`,
`--exclude`, `.git` skipped, a direct file checked
whatever its name, duplicate paths checked once,
`--json` output, `--stdin`, bad flags, missing paths,
empty folders, `--version`, a non-UTF-8 file reported,
input files left unchanged, the tool run from `/` and
under a fake HOME), the bundled examples (sample output
compared against a fresh run, and the README-quoted
outputs checked against it), and hygiene checks (no
placeholder text, no absolute paths, stdlib imports
only, no network use in the source, `.env` first in
`.gitignore`, CI file runs the test file, README names
ShellCheck and the neighbouring repo).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of quoting shell variables is not new, and the
quoting rules follow the same guidance ShellCheck
enforces — but no existing tool does this one job,
checking local shell scripts for unquoted expansions
as a tested command-line gate, as the search above
shows — and every line of code here is original, built
on nothing but Python's standard library.
