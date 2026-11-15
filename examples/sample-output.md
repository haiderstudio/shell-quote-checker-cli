== examples/clean.sh ==
OK — 1 file(s) checked, every expansion quoted.

== examples/flagged.sh ==
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: ${file} line 6 unquoted expansion — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $(ls $file) line 7 unquoted command substitution — quote it or store it in a variable first
FAIL examples/flagged.sh: $@ line 8 unquoted $@ — quote it so each argument stays separate
FAIL examples/flagged.sh: $arg line 9 unquoted variable — quote it so a value with spaces stays one word
Checked 1 file(s), 6 unquoted expansion(s) in 1 file(s).

== examples/edge.sh ==
OK — 1 file(s) checked, every expansion quoted.

== examples/ : the whole folder ==
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $file line 5 unquoted variable — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: ${file} line 6 unquoted expansion — quote it so a value with spaces stays one word
FAIL examples/flagged.sh: $(ls $file) line 7 unquoted command substitution — quote it or store it in a variable first
FAIL examples/flagged.sh: $@ line 8 unquoted $@ — quote it so each argument stays separate
FAIL examples/flagged.sh: $arg line 9 unquoted variable — quote it so a value with spaces stays one word
Checked 4 file(s), 6 unquoted expansion(s) in 1 file(s).
