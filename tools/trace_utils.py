#!/usr/bin/python

import sys
import json
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import sts.replay_event as replay_events
from sts.input_traces.log_parser import parse
from sts.util.tabular import Tabular
from sts.event_dag import EventDag
from collections import Counter

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

class Stats(object):
  def __init__(self):
    self.input_events = Counter()
    self.internal_events = Counter()
    self.message_receives = Counter()
    self.message_sends = Counter()

  def update(self, event):
    if isinstance(event, replay_events.InputEvent):
      event_name = str(event.__class__.__name__)
      self.input_events[event_name] += 1
    else:
      event_name = str(event.__class__.__name__)
      self.internal_events[event_name] += 1
      if event_name == "ControlMessageReceive":
        pkt_class = event.get_packet().__class__.__name__
        self.message_receives[pkt_class] += 1
      elif event_name == "ControlMessageSend":
        pkt_class = event.get_packet().__class__.__name__
        self.message_sends[pkt_class] += 1

  @property
  def input_event_count(self):
    input_count = 0
    for count in self.input_events.values():
      input_count += count
    return input_count

  @property
  def internal_event_count(self):
    internal_count = 0
    for count in self.internal_events.values():
      internal_count += count
    return internal_count

  @property
  def total_event_count(self):
    return self.input_event_count + self.internal_event_count

  def __str__(self):
    s = "Events: %d total (%d input, %d internal).\n" % (self.total_event_count, self.input_event_count, self.internal_event_count)
    if len(self.input_events) > 0:
      s += "\n\tInput events:\n"
      for event_name, count in self.input_events.iteritems():
        s += "\t  %s : %d\n" % (event_name, count)
    if len(self.internal_events) > 0:
      s += "\n\tInternal events:\n"
      for event_name, count in self.internal_events.iteritems():
        s += "\t  %s : %d\n" % (event_name, count)
        if event_name == "ControlMessageReceive":
          for pkt_class, c in self.message_receives.iteritems():
            s += "\t\t  %s : %d\n" % (pkt_class, c)
        if event_name == "ControlMessageSend":
          for pkt_class, c in self.message_sends.iteritems():
            s += "\t\t  %s : %d\n" % (pkt_class, c)
    return s

