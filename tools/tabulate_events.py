#!/usr/bin/env python

# note: must be invoked from the top-level sts directory

import time
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sts.replay_event import *
from sts.dataplane_traces.trace import Trace
from sts.input_traces.log_parser import parse
from tools.pretty_print_input_trace import default_fields, field_formatters

class EventGrouping(object):
  def __init__(self, name):
    self.name = name
    self.events = []

  def append(self, event):
    self.events.append(event)

  def printToConsole(self):
    # TODO(cs): bad feng-shui to have side-effects rather than returning a
    # string. Should refactor field_formatters to not have side-effects
    # either.
    title_str = "====================== %s ======================" % self.name
    print title_str
    for event in self.events:
      for field in default_fields:
        field_formatters[field](event)
    print "=" * len(title_str)

def main(args):
  # N.B. it would be nice to include link discovery or host location discovery
  # events here, but that's specific to the Controller's log output.
  network_failure_events = EventGrouping("Topology Change Events")
  controlplane_failure_events = EventGrouping("Control Plane Blockages")
  controller_failure_events = EventGrouping("Controller Change Events")
  host_events = EventGrouping("Host Migrations")

  event2grouping = {
    SwitchFailure : network_failure_events,
    SwitchRecovery : network_failure_events,
    LinkFailure : network_failure_events,
    LinkRecovery : network_failure_events,
    ControlChannelBlock : controlplane_failure_events,
    ControlChannelUnblock : controlplane_failure_events,
    ControllerFailure : controller_failure_events,
    ControllerRecovery : controller_failure_events,
    BlockControllerPair : controller_failure_events,
    UnblockControllerPair : controller_failure_events,
    HostMigration : host_events,
    # TODO(cs): support TrafficInjection, DataplaneDrop? Might get too noisy.
  }

  with open(args.input) as input_file:
    trace = parse(input_file)
    for event in trace:
      if type(event) in event2grouping:
        event2grouping[type(event)].append(event)

  for grouping in [network_failure_events, controlplane_failure_events,
                   controller_failure_events, host_events]:
    grouping.printToConsole()
    print

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('input', metavar="INPUT",
                      help='The input json file to be printed')
  args = parser.parse_args()

  main(args)
