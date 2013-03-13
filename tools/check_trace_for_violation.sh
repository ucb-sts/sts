#!/bin/bash

trace=$1

if [ "$trace" == "" ]; then
  echo 1>&2 "Usage: $0 <Path to trace file>"
  exit 1
fi

result=`grep InvariantViolation $trace`
if [ "$result" == "" ]; then
  echo "No invariant violation"
else
  echo $result
fi
