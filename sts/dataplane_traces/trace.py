import pickle
from pox.lib.util import assert_type
from pox.lib.packet.ethernet import *
from sts.entities import HostInterface

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

class Trace(object):
  '''Encapsulates a sequence of dataplane events to inject into a simulated network.'''

  def __init__(self, tracefile_path, topology):
    with file(tracefile_path, 'r') as tracefile:
      self.dataplane_trace = pickle.load(tracefile)

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
      return dp_event
