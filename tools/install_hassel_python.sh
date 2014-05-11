#!/bin/bash
#
# Loads and compiles the hassel-python c-extension. This script is idempotent.
# To be invoked from top-level sts directory.

git submodule init
git submodule update

# Mac X-Code quirk:
export ARCHFLAGS=-Wno-error=unused-command-line-argument-hard-error-in-future
(cd sts/hassel/hsa-python && source setup.sh)

