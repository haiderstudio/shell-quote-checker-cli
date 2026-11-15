#!/bin/sh
# Five unquoted expansions — each one breaks when a
# value holds a space.
file=$1
cp $file $file.bak
echo ${file}
echo $(ls $file)
for arg in $@; do
  echo $arg
done
