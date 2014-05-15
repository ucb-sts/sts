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

import pickle
from pox.lib.util import assert_type
from pox.lib.packet.ethernet import *
from sts.entities import HostInterface

import base64
import logging
log = logging.getLogger("dataplane_trace")

class DataplaneEvent (object):
  '''
  Encapsulates a packet injected at a (switch.dpid, port) pair in the network
  Used for trace generation or replay debugging
  '''
  def __init__ (self, interface, packet):
    assert_type("interface", interface, HostInterface, none_ok=False)
    assert_type("packet", packet, ethernet, none_ok=False)
    self.interface = interface
    self.packet = packet

  def to_json(self):
    json_safe_packet = base64.b64encode(self.packet.pack()).replace("\n", "")
    return {'interface' : self.interface.to_json(), 'packet' : json_safe_packet}

  @staticmethod
  def from_json(json_hash):
    interface = HostInterface.from_json(json_hash['interface'])
    raw = base64.b64decode(json_hash['packet'])
    packet = ethernet(raw=raw)
    return DataplaneEvent(interface, packet)

  def __repr__(self):
    return "Interface:%s Packet:%s" % (str(self.interface),
                                       str(self.packet))

class Trace(object):
  '''Encapsulates a sequence of dataplane events to inject into a simulated network.'''

  def __init__(self, tracefile_path, topology=None):
    with file(tracefile_path, 'r') as tracefile:
      self.dataplane_trace = pickle.load(tracefile)

    if topology is not None:
      # Hashmap used to inject packets from the dataplane_trace
      self.interface2host = {
        interface: host
        for host in topology.hosts
        for interface in host.interfaces
      }

      self._type_check_dataplane_trace()

  def _type_check_dataplane_trace(self):
    for dp_event in self.dataplane_trace:
      if dp_event.interface not in self.interface2host:
        raise RuntimeError("Dataplane trace does not type check (%s)" %
                           str(dp_event.interface))

  def peek(self):
    if len(self.dataplane_trace) == 0:
      log.warn("No more trace inputs to inject!")
      return (None, None)
    dp_event = self.dataplane_trace[0]
    host = self.interface2host[dp_event.interface]
    return (dp_event, host)

  def inject_trace_event(self):
    if len(self.dataplane_trace) == 0:
      log.warn("No more trace inputs to inject!")
      return
    else:
      log.info("Injecting trace input")
      dp_event = self.dataplane_trace.pop(0)
      if dp_event.interface not in self.interface2host:
        log.warn("Interface %s not present" % str(dp_event.interface))
        return
      host = self.interface2host[dp_event.interface]
      host.send(dp_event.interface, dp_event.packet)
      return (dp_event, host)
