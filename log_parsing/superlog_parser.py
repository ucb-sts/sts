'''
Parses `superlog`s and returns a list of Event objects, each with their
dependencies filled in.

`superlog` format: Each line is a json hash representing either an internal
event or an external input event.

Event hashes must have at least the following keys:
  'label':            any unique non-whitespace identifier
  'class':            the name of the corresponding python class that
                      encapsulates this event type, e.g. 'LinkFailure'.
                      These classes can be found in sts/event.py

Hashes may have additional custom keys. For example, external input events
must the following key:
  'dependent_labels': list of dependent labels (internal events that will not occur if this
                      event is pruned)
'''

import logging
import json
import sts.event as event
log = logging.getLogger("superlog_parser")

input_name_to_class = {
  klass.__name__ : klass
  for klass in event.all_input_events
}

internal_event_name_to_class {
  klass.__name__ : klass
  for klass in event.all_internal_events
}

def check_unique_label(event_label, existing_event_labels):
  '''Check to make sure that event_label is not in existing_event_labels.
  Throw an exception if this invariant does not hold.

  If the invariant does hold, add event_label to existing_event_labels.'''
  if event_label in existing_event_labels:
    raise RuntimeError("Event label %d already exists!" % event_label)
  existing_event_labels.add(event_label)

def sanity_check_external_input_event(existing_event_labels, dependent_labels,
                                      json_hash):
  '''Takes an external event json hash and checks that invariants hold.
  Raises an exception if they do not hold. Otherwise populates
  dependent_labels'''
  dependents = set(json_hash['dependent_labels'])
  # can't have dependents that have already happened!
  assert(dependents.isdisjoint(existing_event_labels))
  dependent_labels.update(dependents)

def sanity_check_internal_event(existing_event_labels, dependent_labels,
                                json_hash):
  '''Takes an internal event json hash and checks that invariants hold.
  Raises an exception if they do not hold. Otherwise updates
  dependent_labels'''
  dependent_labels.discard(json_hash['label'])

def parse(logfile_path):
  '''Input: path to a logfile.

  Output: A list of all the internal and external events in the order in which
  they exist in the logfile. Each internal event is annotated with the set of
  source events that are necessary conditions for its occurence.'''

  # the return value of the parsed log
  trace = []
  # a set of all event labels
  event_labels = set()
  # dependent labels that have to be satisfied by future internal events
  dependent_labels = set()

  with open(logfile_path, 'r') as log_file:
    for line in log_file:
      try:
        json_hash = json.loads(line.rstrip())
        check_unique_label(json_hash['label'], event_labels)
        if json_hash['class'] in input_name_to_class:
          sanity_check_external_input_event(existing_event_labels,
                                            dependent_labels,
                                            json_hash)
          event = input_name_to_class[json['class']](json_hash)
         elif json_hash['class'] in internal_event_name_to_class:
           sanity_check_internal_event(existing_event_labels, dependent_labels,
                                       json_hash)
           event = internal_event_name_to_class[json['class']](json_hash)
         else:
           log.warn("Unknown class type %s" % json_hash['class'])
         trace.append(event)
      else:
       log.warn("Ignoring unknown line format: " % line)

  # all the foward dependencies should be satisfied!
  assert(len(dependent_labels) == 0)

  return trace
