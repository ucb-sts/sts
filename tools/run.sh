#!/bin/bash

((
success=0
))

while [ true ]; do
    $*
    if [ $? -eq 0 ]; then
        (( success++ ))
    else
        echo "Failure Found!"
        exit 0
    fi
    echo 'run.sh killing'
    ps ax | grep pox | grep -v vi | grep -v grep | grep -v fuzz_pox_mesh | awk -F ' ' ' { print $1 }' | xargs kill -9
    sleep 1
done

echo "Successes before failure: $success"
