#!/usr/bin/env python

# note: must be invoked from the top-level sts directory

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sts.dataplane_traces.trace_generator import generate_example_trace_same_subnet

# TODO(cs): output filename should be a parameter
generate_example_trace_same_subnet(num_switches=2)
