#!/usr/bin/env python

# Note: must be invoked from the top-level sts directory

import json
import time
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import sts.replay_event as replay_events

parser = argparse.ArgumentParser()
parser.add_argument('input', metavar="INPUT",
                    help='The input json file to be printed')
parser.add_argument('-f', '--format-file',
                    help='The output format configuration file',
                    default=None)
parser.add_argument('-N', '--no-stats', action="store_false", dest="stats",
                    help="Don't print statistics",
                    default=True)
args = parser.parse_args()

# ------------------------------- Config file format: --------------------------------------
# Config files are python modules that may define the following variables:
#   fields  => an array of field names to print. Uses default_fields if undefined.
#   filtered_classes => a set of classes to ignore, from sts.replay_event
#   ...
#
# See example_pretty_print_config.py for an example.
# ------------------------------------------------------------------------------------------

default_fields = ['class_with_label', 'fingerprint', 'event_delimiter']
default_filtered_classes = set()

def class_printer(event):
  print event.__class__.__name__

def class_with_label_printer(event):
  print (event.label + ' ' + event.__class__.__name__ +
         ' (' + ("prunable" if event.prunable else "unprunable") + ')')

def fingerprint_printer(event):
  fingerprint = None
  if hasattr(event, 'fingerprint'):
    # The first element of the fingerprint tuple is always the class name, so
    # we skip it over
    # TODO(cs): make sure that dict fields are always in the same order
    fingerprint = event.fingerprint[1:]
  print "Fingerprint: ", fingerprint

def _timestamp_to_string(timestamp):
  sec = timestamp[0]
  micro_sec = timestamp[1]
  epoch = float(sec) + float(micro_sec) / 1e6
  struct_time = time.localtime(epoch)
  # Hour:Minute:Second
  no_micro = time.strftime("%X", struct_time)
  # Hour:Minute:Second:Microsecond
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

class Stats:
  def __init__(self):
    self.input_events = 0
    self.internal_events = 0

  def update(self, event):
    if isinstance(event, replay_events.InputEvent):
      self.input_events += 1
    else:
      self.internal_events += 1

  @property
  def total_events(self):
    return self.input_events + self.internal_events

  def __str__(self):
    return "Events: %d total (%d input, %d internal)." % (self.total_events, self.input_events, self.internal_events)

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

  if hasattr(format_def, "fields"):
    fields = format_def.fields
  else:
    fields = default_fields

  if hasattr(format_def, "filtered_classes"):
    filtered_classes = format_def.filtered_classes
  else:
    filtered_classes = default_filtered_classes

  name_to_class = {
    klass.__name__ : klass
    for klass in replay_events.all_events
  }
  stats = Stats()

  # All events are printed with a fixed number of lines, and (optionally)
  # separated by delimiter lines of the form:
  # ----------------------------------
  with open(args.input) as input_file:
    for line in input_file:
      try:
        json_hash = json.loads(line.rstrip())
        event = name_to_class[json_hash['class']].from_json(json_hash)
        if type(event) not in filtered_classes:
          for field in fields:
            if field not in field_formatters:
              raise ValueError("Unknown field %s" % field)
            field_formatters[field](event)
        stats.update(event)
      except:
        print >> sys.stderr, "Corrupt json hash found %s" % line

  if args.stats:
    print "Stats: %s" % stats

if __name__ == '__main__':
  main(args)
