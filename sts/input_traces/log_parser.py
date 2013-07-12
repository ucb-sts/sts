# Copyright 2011-2013 Colin Scott
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''
Parses `superlog's and returns a list of sts.event.Event objects

`superlog' format: Each line is a json hash representing either an internal
event or an external input event.

Event hashes must have at least the following keys:
  'label':            any unique identifier
  'class':            the name of the corresponding python class that
                      encapsulates this event type, e.g. 'LinkFailure'.
                      These classes can be found in sts/event.py

Hashes may have additional custom keys. For example, external input events
must the following key:
  'dependent_labels': list of dependent labels (internal events that will not occur if this
                      event is pruned)
'''

import json
import sts.replay_event as event
import logging
log = logging.getLogger("superlog_parser")

input_name_to_class = {
  klass.__name__ : klass
  for klass in event.all_input_events
}

internal_event_name_to_class = {
  klass.__name__ : klass
  for klass in event.all_internal_events
}

special_event_name_to_class = {
  klass.__name__ : klass
  for klass in event.all_special_events
}

def check_unique_label(event_label, existing_event_labels):
  '''Check to make sure that event_label is not in existing_event_labels.
  Throw an exception if this invariant does not hold.

  If the invariant does hold, add event_label to existing_event_labels.'''
  if event_label in existing_event_labels:
    raise RuntimeError("Event label %s already exists!" % event_label)
  existing_event_labels.add(event_label)

def sanity_check_external_input_event(existing_event_labels, dependent_labels,
                                      json_hash):
  '''Takes an external event json hash and checks that no dependents have
  already occured. Raises an exception if any have, otherwise populates
  dependent_labels'''
  dependents = set(json_hash['dependent_labels'])
  # can't have dependents that have already happened!
  assert(dependents.isdisjoint(existing_event_labels))
  dependent_labels.update(dependents)
  # External input events can be dependents too (e.g. link recoveries are
  # dependents of link failures)
  dependent_labels.discard(json_hash['label'])

def sanity_check_internal_event(existing_event_labels, dependent_labels,
                                json_hash):
  '''Takes an internal event json hash and removes it from the set of
  dependent labels that must be present before the end of the log.
  '''
  dependent_labels.discard(json_hash['label'])

def parse_path(logfile_path):
  '''Input: path to a logfile.

  Output: A list of all the internal and external events in the order in which
  they exist in the logfile. Each internal event is annotated with the set of
  source events that are necessary conditions for its occurence.'''
  with open(logfile_path) as logfile:
    return parse(logfile)

def check_legacy_format(json_hash):
  if (hasattr(json_hash, 'controller_id') and
      type(json_hash.controller_id) == list):
    # TODO(cs): translate rather than throwing up
    raise ValueError("Legacy controller id. Should be a string label: %s" % json_hash.controller_id)
  if not hasattr(json_hash, 'round'):
    # Insert a dummy round number
    json_hash['round'] = -1

def parse(logfile):
  '''Input: logfile.

  Output: A list of all the internal and external events in the order in which
  they exist in the logfile. Each internal event is annotated with the set of
  source events that are necessary conditions for its occurence.'''

  # the return value of the parsed log
  trace = []
  # a set of all event labels
  event_labels = set()
  # dependent labels that must be present somewhere in the log.
  dependent_labels = set()

  for line in logfile:
    json_hash = json.loads(line.rstrip())
    check_unique_label(json_hash['label'], event_labels)
    check_legacy_format(json_hash)
    if json_hash['class'] in input_name_to_class:
      sanity_check_external_input_event(event_labels,
                                        dependent_labels,
                                        json_hash)
      event = input_name_to_class[json_hash['class']].from_json(json_hash)
    elif json_hash['class'] in internal_event_name_to_class:
      sanity_check_internal_event(event_labels, dependent_labels,
                                  json_hash)
      event = internal_event_name_to_class[json_hash['class']].from_json(json_hash)
    elif json_hash['class'] in special_event_name_to_class:
      event = special_event_name_to_class[json_hash['class']].from_json(json_hash)
    else:
      print "Warning: Unknown class type %s" % json_hash['class']
      continue
    trace.append(event)

  # all the foward dependencies should be satisfied!
  assert(len(dependent_labels) == 0)

  return trace
