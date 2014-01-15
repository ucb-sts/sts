#!/usr/bin/python

# output format, one line per subsequence where a bug was found:
# <Subsequence #> <# inputs> <event 1 included?> <event 2 included?> ...

import argparse
import json
import glob
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sts.input_traces.log_parser import parse
from sts.util.tabular import Tabular
from sts.event_dag import EventDag

class InterReplayDirectory(object):
  def __init__(self, dir_str):
    self.dir_str = dir_str
    # Format example: interreplay_10_r_5/
    self.index = int(os.path.basename(dir_str).split("_")[1])

  def __str__(self):
    return self.dir_str

  def __repr__(self):
    return self.dir_str

def parse_json(subsequence_violations_path):
  with open(subsequence_violations_path) as json_data:
    d = json.load(json_data)
    # Convert strings to integers
    for k,v in d.iteritems():
      if type(k) != int:
        del d[k]
        d[int(k)] = v
    return d

def parse_event_trace(trace_path):
  with open(trace_path) as input_file:
    return EventDag(parse(input_file))

def format_trace(label, trace, full_trace):
  row = [label, len(trace.input_events)]
  isect = set(trace.input_events).intersection(set(full_trace.input_events))
  for input_event in full_trace.input_events:
    if input_event in isect:
      row.append(1)
    else:
      row.append(0)
  return row

def main(args):
  # Grab JSON of which subsequences triggered a bug.
  replay_idx_to_violation = parse_json(args.subsequence_violations)

  subsequence_dirs = [ InterReplayDirectory(d) for d in
                       glob.glob(args.directory + "/interreplay_*") ]
  assert(subsequence_dirs != [])
  subsequence_dirs.sort(key=lambda d: d.index)

  # First, grab all inputs so we know how to format
  repro_dir = subsequence_dirs.pop(0)
  assert(os.path.basename(str(repro_dir)) == "interreplay_0_reproducibility")
  full_trace = parse_event_trace(str(repro_dir) + "/events.trace")

  # Now format each subsequence
  columns = []
  columns.append(["subsequence", lambda row: row[0]])
  columns.append(["# inputs", lambda row: row[1]])
  for idx, e in enumerate(full_trace.input_events):
    # See: http://stackoverflow.com/questions/233673/lexical-closures-in-python
    def bind_closure(index):
      return lambda row: row[index+2]
    columns.append([e.label, bind_closure(idx)])
  t = Tabular(columns)
  rows = []
  for subsequence_dir in subsequence_dirs:
    if "_final_mcs_trace" in str(subsequence_dir):
      # Make sure to always print the final MCS
      trace = parse_event_trace(str(subsequence_dir) + "/events.trace")
      rows.append(format_trace("MCS", trace, full_trace))
    elif replay_idx_to_violation[subsequence_dir.index]:
      # Otherwise only consider subsequences that resulted in a violation
      trace = parse_event_trace(str(subsequence_dir) + "/events.trace")
      rows.append(format_trace(subsequence_dir.index, trace, full_trace))

  t.show(rows)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-s', '--subsequence-violations', dest='subsequence_violations',
                      help=('''JSON file containing a dict of which subsequences'''
                           ''' resulted in a violation.'''),
                      required=True)
  parser.add_argument('-d', '--directory',
                      help='path to top-level MCS experiment results directory',
                      required=True)
  args = parser.parse_args()

  main(args)
