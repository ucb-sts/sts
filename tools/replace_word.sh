#!/bin/bash

if [ $# < 3 ]; then
  echo "Usage: replace_word.sh [word_to_replace] [new word] [directory]"
  exit
fi

BEFORE=$1
AFTER=$2
DIRECTORY=$3
FILES=$(find $DIRECTORY)

for f in $FILES; do
  if ! [ -f $f ]; then
    echo "Not a file: $f. Skipping!"
    continue 
  fi
  CONTENT=$(sed s/$1/$2/g $f)
  echo -e "$CONTENT" > $f
  echo "Replaced $1 with $2 in $f"
done

echo "Success!"

