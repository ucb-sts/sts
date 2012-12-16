#!/bin/bash

# TODO(cs): automatically cut off lines above rcs@?
grep -v ":input_logger:" $1 | grep -v ":events:" | grep -v "  xid" \
    | egrep -v "^Round [0-9]*" | grep -v "Checking controller liveness..."\
    | grep -v "No correctness violations" | grep -v "buffer_id:" \
    | grep -v ":event_scheduler:" > buf && mv buf $1
