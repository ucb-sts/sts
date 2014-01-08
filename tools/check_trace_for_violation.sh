#!/bin/bash

# NOTE: this tool tells you whether any InvariantViolation occured, anywhere
# in the trace. If you need to know whether a particular violation signature
# occured (in the case where there are multiple invariant violations), or
# whether an InvariantViolation occured at the end of the trace, use
# tools/pretty_print_event_trace.py -s

trace=$1
non_verbose=$2

if [ "$trace" == "" ]; then
  echo 1>&2 "Usage: $0 <Path to trace file>"
  exit 1
fi

result=`grep InvariantViolation $trace`
if [ "$result" == "" ]; then
  echo "No invariant violation"
else
  if [ "$non_verbose" != "" ]; then
      echo "Violation"
  else
      echo $result
  fi
fi
