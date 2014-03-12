#!/usr/bin/env python

# note: must be invoked from the top-level sts directory

import time
import argparse
import os
import sys
from collections import Counter

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from trace_utils import parse_event_trace, Stats
from pretty_print_input_trace import default_fields, field_formatters
import sts.replay_event as replay_events
from sts.dataplane_traces.trace import Trace
from sts.input_traces.log_parser import parse

def l_minus_r(l, r):
  result = []
  r_fingerprints = Counter([e.fingerprint for e in r.events])
  for e in l.events:
    if e.fingerprint not in r_fingerprints:
      result.append(e)
    else:
      r_fingerprints[e] -= 1
      if r_fingerprints[e] == 0:
        del r_fingerprints[e]
  return result

def main(args):
  trace1 = parse_event_trace(args.trace1)
  trace2 = parse_event_trace(args.trace2)

  if args.ignore_inputs:
    filtered_classes = set(replay_events.all_input_events)
  else:
    filtered_classes = set()

  print "Events in trace1, not in trace2"
  print "================================="
  t1_t2_stats = Stats()
  for e in l_minus_r(trace1, trace2):
    if type(e) not in filtered_classes:
      t1_t2_stats.update(e)
      for field in default_fields:
        field_formatters[field](e)
  print str(t1_t2_stats)

  print "Events in trace2, not in trace1"
  print "================================="
  t2_t1_stats = Stats()
  for e in l_minus_r(trace2, trace1):
    if type(e) not in filtered_classes:
      t2_t1_stats.update(e)
      for field in default_fields:
        field_formatters[field](e)
  print str(t2_t1_stats)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('trace1', metavar="TRACE1",
                      help='The first input json file to be diffed')
  parser.add_argument('trace2', metavar="TRACE2",
                      help='The second input json file to be diffed')
  parser.add_argument('-i', '--ignore-inputs',
                      dest="ignore_inputs", default=True,
                      help='''Whether to ignore inputs ''')
  args = parser.parse_args()

  main(args)
