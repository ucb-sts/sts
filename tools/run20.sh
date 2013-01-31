#!/bin/bash

((
success=0
))

((
failures=0
))

for i in `seq 20`; do
    $*
    if [ $? -eq 0 ]; then
        (( success++ ))
    else
        (( failures++ ))
    fi
    echo 'run.sh killing'
    ps ax | grep pox | grep -v vi | grep -v grep | grep -v fuzz_pox_mesh | awk -F ' ' ' { print $1 }' | xargs --no-run-if-empty kill -9
    sleep 1
done

echo "Successes: $success, Failures: $failures"
