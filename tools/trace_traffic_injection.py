#!/usr/bin/env python

# note: must be invoked from the top-level sts directory

# TODO(cs): need unique ids for every packet in the network. If there
# are multiple in-flight packets with the same headers, this tool conflates
# them.

import time
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "../pox"))

from pox.openflow.libopenflow_01 import *
from pox.lib.packet.ethernet import *
import sts.replay_event as replay_events
from sts.dataplane_traces.trace import Trace
from sts.input_traces.log_parser import parse
from sts.fingerprints.messages import DPFingerprint
from tools.pretty_print_input_trace import field_formatters, default_fields

def ti_filter(e, pkt_fingerprint):
  return DPFingerprint.from_pkt(e.dp_event.packet) == pkt_fingerprint

dp_ofp_packets = set([ofp_packet_in, ofp_packet_out])

def control_message_filter(e, pkt_fingerprint):
  of_pkt = e.get_packet()

  # TODO(cs): also handle ofp_flow_mod.buffer_id, which applies the rule to a
  # particular buffered packet.
  if type(of_pkt) not in dp_ofp_packets:
    return False

  # TODO(cs): problem: controllers often truncate the packet in
  # ofp_packet_out.data. ofp_packet_in's are fine though, since POX's
  # software_switch always includes the entire dataplane packet in the
  # packet_in. To really solve this issue we would need to replay the
  # flow_mods to cloned topology, and verify that buffer_id's are chosen
  # deterministically.
  return DPFingerprint.from_pkt(ethernet(raw=of_pkt.data)) == pkt_fingerprint

def dp_forward_filter(e, pkt_fingerprint):
  return e.dp_fingerprint == pkt_fingerprint

def process_flow_mod_filter(e, pkt_fingerprint):
  # TODO(cs): implement me.
  pass

dp_class_to_filter = {
  replay_events.TrafficInjection : ti_filter,
  replay_events.ControlMessageReceive : control_message_filter,
  replay_events.ControlMessageSend : control_message_filter,
  replay_events.DataplanePermit : dp_forward_filter,
  replay_events.DataplaneDrop : dp_forward_filter,
  replay_events.ProcessFlowMod : process_flow_mod_filter,
}

def main(args):
  with open(args.input) as input_file:
    trace = parse(input_file)
    # TODO(cs): binary search instead of linear?
    while len(trace) > 0 and trace[0].label_id < args.ti_id:
      trace.pop(0)

    ti_event = trace[0]
    if type(ti_event) != replay_events.TrafficInjection:
      raise ValueError("Event %s with is not a TrafficInjection" % str(ti_event))

    pkt_fingerprint = DPFingerprint.from_pkt(ti_event.dp_event.packet)

    for event in trace:
      t = type(event)
      if t in dp_class_to_filter and dp_class_to_filter[t](event, pkt_fingerprint):
        for field in default_fields:
          field_formatters[field](event)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('input', metavar="INPUT",
                      help='The input json file to be printed')
  parser.add_argument('ti_id', metavar="TRAFFIC_INJECTION_ID",
                      help='The event number of the traffic injection event to trace')
  args = parser.parse_args()
  if args.ti_id[0] == "e" or args.ti_id[0] == "i":
    args.ti_id = args.ti_id[1:]
  args.ti_id = int(args.ti_id)

  main(args)
