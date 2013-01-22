#!/usr/bin/env python

import json
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-i', '--input', required=True,
                    help='The input json file to be printed')
parser.add_argument('-f', '--format-file',
                    help='The output format configuration file',
                    default=None)
args = parser.parse_args()

# ------------------------------- Config file format: --------------------------------------
# Config files are python modules that may define the following variables:
#   fields  => an array of field names to print. Uses default_fields if undefined.
#   ...
#
# See pretty_print_config.py for an example.
# TODO(cs): allow user to filter out events types
# ------------------------------------------------------------------------------------------

default_fields = ['class_with_label', 'fingerprint', 'event_delimiter']

def class_printer(json_hash):
  print json_hash['class']

def class_with_label_printer(json_hash):
  print json_hash['label'] + ' ' + json_hash['class']

def fingerprint_printer(json_hash):
  fingerprint = None
  if 'fingerprint' in json_hash:
    # The first element of the fingerprint tuple is always the class name, so
    # we skip it over
    # TODO(cs): make sure that dict fields are always in the same order
    fingerprint = json_hash['fingerprint'][1:]
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

def abs_time_printer(json_hash):
 print _timestamp_to_string(json_hash['time'])

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

  # All events are printed with a fixed number of lines, and (optionally)
  # separated by delimiter lines of the form:
  # ----------------------------------
  with open(args.input) as input_file:
    for line in input_file:
      json_hash = json.loads(line.rstrip())
      for field in fields:
        if field not in field_formatters:
          raise ValueError("Unknown field %s" % field)
        field_formatters[field](json_hash)

if __name__ == '__main__':
  main(args)
