#!/bin/bash

# To be invoked from sts root directory 
USAGE="Usage: ./tools/fuzz_many_times.py [iterations] [config]"
if [[ $# -ne 2 ]]; then
  echo $USAGE
  exit 1
fi

# Number of iterations
re='^[0-9]+$'
if ! [[ $1 =~ $re ]] || [[ $1 -lt 1 ]] || [[ $1 -gt 100 ]]; then
  echo "Number of iterations must be a number between 1 and 100!"
  echo $USAGE
  exit 1
fi

# Config path
if ! [[ -f $2 ]] ; then
  echo "$2 is not a valid file!"
  echo $USAGE
  exit 1
fi
EXP_NAME=$(basename $2)
EXP_NAME=${EXP_NAME%.*}

# Run simulator 
for i in $(seq 1 $1)
do
  echo -e "\n==================== Starting the $i'th iteration ====================\n"
  ./simulator.py -c $2
  mv experiments/"$EXP_NAME" experiments/"$EXP_NAME"_"$i"
done
