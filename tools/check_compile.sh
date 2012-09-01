#!/bin/bash

find . -name "*py" | grep -v pypy | xargs python -m py_compile
