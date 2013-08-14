#!/bin/bash

if [ $# -le 3 ]; then
  echo "Usage: replace_word.sh [word_to_replace] [new word] [files]"
  exit
fi

BEFORE=$1
AFTER=$2
FILES=${@:3}

for f in $FILES; do
  if ! [ -f $f ]; then
    echo "Not a file: $f. Skipping!"
    continue 
  fi
  CONTENT=$(sed s/$1/$2/g $f)
  printf "$CONTENT" > $f
  echo "Replaced $1 with $2 in $f"
done

echo "Success!"

