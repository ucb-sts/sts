#!/bin/bash
# Invoke with: ./tools/clean.sh

if [ -f .project ]; then
    cp .project .pydevproject /tmp
fi

git clean -fX

if [ -f .project ]; then
    cp /tmp/.project /tmp/.pydevproject .
fi

cd sts/hassel/hassel-c
make

