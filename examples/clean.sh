#!/bin/sh
# Every expansion in this script is quoted, or sits
# where word-splitting cannot happen.
file="$1"
echo "Processing $file"
cp "$file" "$file.bak"

if [ -n "$file" ]; then
  echo "got $file"
fi

# The right-hand side of an assignment never splits.
dest=$file.bak
echo "saved to $dest"

# No splitting happens inside [[ ]].
if [[ -n $file ]]; then
  echo "still here"
fi

# A quoted command substitution is safe.
listing="$(ls "$file")"
echo "$listing"
