#!/bin/bash

find . -name "*.py" | grep -v pypy | egrep -v "^./experiments" | xargs python -m py_compile
