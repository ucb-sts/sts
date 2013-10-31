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

rm -rf experiments/"$EXP_NAME"_no_violations
rm -rf experiments/"$EXP_NAME"_irreproducible
mkdir experiments/"$EXP_NAME"_no_violations
mkdir experiments/"$EXP_NAME"_irreproducible

NUM_REPLAYS=5

# Run simulator 
for i in $(seq 1 $1)
do
  echo -e "\n==================== Starting the $i'th iteration ====================\n"
  # Run Fuzzer
  ./simulator.py -c $2
  NEW_EXP_NAME="$EXP_NAME"_"$i"
  mv experiments/"$EXP_NAME" experiments/"$NEW_EXP_NAME"
  tools/replace_word.sh "$EXP_NAME" "$NEW_EXP_NAME" experiments/"$NEW_EXP_NAME"
  NO_VIOLATION=$(tail -n 100 experiments/"$NEW_EXP_NAME"/simulator.out | grep "Round 500 completed")
  if [[ ! -z "$NO_VIOLATION" ]]; then
    echo "$NEW_EXP_NAME has no violations!"
    mv experiments/"$NEW_EXP_NAME" experiments/"$EXP_NAME"_no_violations
    continue
  fi
  # Run Replayer up to NUM_REPLAYS times
  for j in $(seq 1 $NUM_REPLAYS)
  do
    ./simulator.py -c experiments/"$NEW_EXP_NAME"/replay_config.py
    REPLAY_NO_VIOLATION=$(tail -n 100 experiments/"$NEW_EXP_NAME"_replay/simulator.out | grep "No correctness violations")
    if [[ -z "$REPLAY_NO_VIOLATION" ]]; then
      break
    fi
    if [[ $j -eq $NUM_REPLAYS ]]; then
      echo "Cannot reproduce $NEW_EXP_NAME violation!"
      mv experiments/"$NEW_EXP_NAME" experiments/"$EXP_NAME"_irreproducible
      mv experiments/"$NEW_EXP_NAME"_replay experiments/"$EXP_NAME"_irreproducible
      break
    fi
  done
done

