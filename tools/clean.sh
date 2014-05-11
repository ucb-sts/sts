#!/bin/bash
# Invoke with: ./tools/clean.sh

no_compile=$1

if [ -f .project ]; then
    cp .project .pydevproject /tmp
fi

git clean -fX
(cd pox && git clean -fX)
(cd sts/hassel && git clean -fX)

if [ -f .project ]; then
    cp /tmp/.project /tmp/.pydevproject .
fi

if [ "$no_compile" == "" ]; then
  export ARCHFLAGS=-Wno-error=unused-command-line-argument-hard-error-in-future
  (cd sts/hassel/hsa-python && source setup.sh)
  (cd sts/hassel/hassel-c && make)
fi

