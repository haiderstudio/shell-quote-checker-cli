#!/bin/sh
# Tricky cases that are all safe, and pass.
file="my file.txt"

# Single quotes, comments, and escaped dollars.
echo '$file stays literal'
# echo $file in a comment stays a comment
echo \$file stays literal

# Single-word values never split.
echo "args: $# status: $? pid: $$"

# The case subject and an arithmetic block are safe.
case $file in
  *.txt) echo "text file" ;;
esac
count=$((1 + 2))
echo "count is $count"

# A heredoc body is skipped, even with $file in it.
cat <<EOF
The file is $file
EOF

# A herestring does not split either.
grep error <<< $file

# Positional and length expansions are single words.
echo ${10} ${#file}
