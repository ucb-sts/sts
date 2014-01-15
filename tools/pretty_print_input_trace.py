#!/usr/bin/env python

# note: must be invoked from the top-level sts directory

import time
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import sts.replay_event as replay_events
from sts.dataplane_traces.trace import Trace
from sts.input_traces.log_parser import parse
from trace_utils import Stats

default_fields = ['class_with_label', 'fingerprint', 'event_delimiter']
default_filtered_classes = set()

def class_printer(event):
  print event.__class__.__name__

def class_with_label_printer(event):
  print (event.label + ' ' + event.__class__.__name__ +
         ' (' + ("prunable" if event.prunable else "unprunable") + ')')

def round_printer(event):
  print "round: %d" % event.round

def fingerprint_printer(event):
  fingerprint = None
  if hasattr(event, "pretty_print_fingerprint"):
    fingerprint = event.pretty_print_fingerprint()
  elif hasattr(event, 'fingerprint'):
    # the first element of the fingerprint tuple is always the class name, so
    # we skip it over
    # TODO(cs): make sure that dict fields are always in the same order
    fingerprint = event.fingerprint[1:]
  print "fingerprint: ", fingerprint

def _timestamp_to_string(timestamp):
  sec = timestamp[0]
  micro_sec = timestamp[1]
  epoch = float(sec) + float(micro_sec) / 1e6
  struct_time = time.localtime(epoch)
  # hour:minute:second
  no_micro = time.strftime("%X", struct_time)
  # hour:minute:second:microsecond
  with_micro = no_micro + ":%d" % micro_sec
  return with_micro

def abs_time_printer(event):
  print _timestamp_to_string(event.time)

def event_delim_printer(_):
  print "--------------------------------------------------------------------"

field_formatters = {
  'class_with_label' : class_with_label_printer,
  'class' : class_printer,
  'fingerprint' : fingerprint_printer,
  'event_delimiter' : event_delim_printer,
  'abs_time' : abs_time_printer,
  # TODO(cs): allow user to display relative time between events
}


def check_for_violation_signature(trace, signature):
  for event in reversed(trace):
    # TODO(cs): this algorithm is broken in the case that InvariantViolations
    # were part of the original events.trace as internal/special events. The
    # last InvariantViolation in the trace is not necessarily the one that
    # was checked by mcs_finder. A cleaner way to check for violations would be
    # to store whether or not a violation was found for each run in runtime
    # stats.
    if type(event) == replay_events.WaitTime:
      continue
    if type(event) != replay_events.InvariantViolation:
       # No InvariantViolation occured at the end of the trace
       return False
    return signature in event.violations
  return False

def main(args):
  def load_format_file(format_file):
    if format_file.endswith('.py'):
      format_file = format_file[:-3].replace("/", ".")
    config = __import__(format_file, globals(), locals(), ["*"])
    return config

  if args.format_file is not None:
    format_def = load_format_file(args.format_file)
  else:
    format_def = object()

  dp_trace = None
  if args.dp_trace_path is not None:
    dp_trace = Trace(args.dp_trace_path).dataplane_trace

  if hasattr(format_def, "fields"):
    fields = format_def.fields
  else:
    fields = default_fields

  for field in fields:
    if field not in field_formatters:
      raise ValueError("unknown field %s" % field)

  if hasattr(format_def, "filtered_classes"):
    filtered_classes = format_def.filtered_classes
  else:
    filtered_classes = default_filtered_classes

  stats = Stats()

  # all events are printed with a fixed number of lines, and (optionally)
  # separated by delimiter lines of the form:
  # ----------------------------------
  with open(args.input) as input_file:
    trace = parse(input_file)
    for event in trace:
      if type(event) not in filtered_classes:
        if dp_trace is not None and type(event) == replay_events.TrafficInjection:
          event.dp_event = dp_trace.pop(0)
        for field in fields:
          field_formatters[field](event)
        stats.update(event)

    if check_for_violation_signature(trace, args.violation_signature):
      print "Violation occurs at end of trace: %s" % args.violation_signature
    elif args.violation_signature is not None:
      print ("Violation does not occur at end of trace: %s",
             args.violation_signature)
    print

  if args.stats:
    print "Stats: %s" % stats

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('input', metavar="INPUT",
                      help='The input json file to be printed')
  parser.add_argument('-f', '--format-file',
                      help=str('''The output format configuration file.'''
  ''' ----- config file format: ----'''
  ''' config files are python modules that may define the following variables: '''
  '''   fields  => an array of field names to print. uses default_fields if undefined. '''
  '''   filtered_classes => a set of classes to ignore, from sts.replay_event'''
  '''   ... '''
  ''' see example_pretty_print_config.py for an example. '''
  ''' ---------------------------------'''),
                      default=None)
  parser.add_argument('-n', '--no-stats', action="store_false", dest="stats",
                      help="don't print statistics",
                      default=True)
  parser.add_argument('-d', '--dp-trace-path', dest="dp_trace_path",
                      help="for older traces, specify path to the TrafficInjection packets",
                      default=None)
  parser.add_argument('-s', '--violation-signature', dest="violation_signature",
                      help=('''Check whether the given violation signature '''
                            '''(return value from InvariantChecker), '''
                            '''specified as a string, occurs at the end '''
                            '''of the trace'''),
                      default=None)
  args = parser.parse_args()

  main(args)
