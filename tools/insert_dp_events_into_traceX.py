#!/usr/bin/env python

import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import sts.replay_event as replay_events
from sts.dataplane_traces.trace import Trace
from sts.input_traces.input_logger import InputLogger
from sts.input_traces.log_parser import parse

def main(args):
  if args.dp_trace_path is None:
    args.dp_trace_path = os.path.dirname(args.input) + "/dataplane.trace"

  dp_trace = Trace(args.dp_trace_path).dataplane_trace

  event_logger = InputLogger()
  event_logger.open(results_dir="/tmp/events.trace")

  with open(args.input) as input_file:
    trace = parse(input_file)
    for event in trace:
      if type(event) == replay_events.TrafficInjection:
        event.dp_event = dp_trace.pop(0)
      event_logger.log_input_event(event)

    event_logger.output.close()

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('input', metavar="INPUT",
                      help='The input json file to be printed')
  parser.add_argument('-d', '--dp-trace-path', dest="dp_trace_path", default=None,
                      help='''Optional path to the dataplane trace file. '''
                           ''' Default: `dirname`/dataplane.trace ''')
  args = parser.parse_args()

  main(args)
