# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2012-2012 Kyriakos Zarifis
# Copyright 2014      Ahmed El-Hassany
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


import itertools
from collections import defaultdict
from collections import Iterable
import logging

from pox.openflow.software_switch import DpPacketOut
from pox.openflow.software_switch import SoftwareSwitch
from pox.lib.revent import EventMixin

from sts.entities.hosts import HostAbstractClass
from sts.fingerprints.messages import DPFingerprint
from sts.invariant_checker import InvariantChecker
from sts.util.capability import Capabilities
from sts.util.console import msg


log = logging.getLogger("sts.topology.packet_delivery")


class DataPathBufferCapabilities(Capabilities):
  def __init__(self, can_queue_dp_events=True, can_permit_dp_event=True,
               can_drop_dp_event=True):
    self._can_permit_dp_event = can_permit_dp_event
    self._can_drop_dp_event = can_drop_dp_event
    self._can_queue_dp_events = can_queue_dp_events

  @property
  def can_permit_dp_event(self):
    return self._can_permit_dp_event

  @property
  def can_drop_dp_event(self):
    return self._can_drop_dp_event

  @property
  def can_queue_dp_events(self):
    return self._can_queue_dp_events


class DataPathBuffer(object):
  """
  A Patch panel. Contains a bunch of wires to forward packets between switches.
  Listens to the SwitchDPPacketOut event on the switches.
  """
  def __init__(self, switches=None, hosts=None, connected_port_mapping=None,
               capabilities=None):
    """
    Constructor
     - switches: a list of the switches in the network
     - hosts: a list of hosts in the network
     - connected_port_mapping: a function which takes
                              (switch_no, port_no, dpid2switch),
                               and returns the adjacent (node, port) or None
    """
    if capabilities is None:
      self.capabilities = DataPathBufferCapabilities(can_queue_dp_events=False,
                                                     can_permit_dp_event=False,
                                                     can_drop_dp_event=False)
    else:
      self.capabilities = capabilities
    if switches is None:
      switches = []
    if not isinstance(switches, Iterable):
      switches = [switches]
    if hosts is None:
      hosts = []
    if not isinstance(hosts, Iterable):
      hosts = [hosts]

    self.switches = []
    self.hosts = []
    self.get_connected_port = connected_port_mapping

    for switch in sorted(switches, key=lambda(sw): sw.dpid):
      self.add_switch(switch)
    for host in hosts:
      self.add_host(host)

  def add_switch(self, switch):
    switch.addListener(DpPacketOut, self.handle_DpPacketOut)
    self.switches.append(switch)

  def remove_switch(self, switch):
    switch.removeListener(self.handle_DpPacketOut)
    self.switches.remove(switch)

  def add_host(self, host):
    host.addListener(DpPacketOut, self.handle_DpPacketOut)
    self.hosts.append(host)

  def remove_host(self, host):
    host.removeListener(self.handle_DpPacketOut)
    self.hosts.remove(host)

  def register_interface_pair(self, event):
    (src_addr, dst_addr) = (event.packet.src, event.packet.dst)
    if src_addr is not None and dst_addr is not None:
      InvariantChecker.register_interface_pair(src_addr, dst_addr)

  def handle_DpPacketOut(self, event):
    self.register_interface_pair(event)
    try:
      (node, port) = self.get_connected_port(event.node, event.port)
    except ValueError:
      log.warn("no such port %s on node %s" % (
        str(event.port), str(event.node)))
      return
    if isinstance(node, HostAbstractClass):
      self.deliver_packet(node, event.packet, port)
    else:
      self.forward_packet(node, event.packet, port)

  def forward_packet(self, next_switch, packet, next_port):
    """Forward the packet to the given port"""
    if type(next_port) != int:
      next_port = next_port.port_no
    next_switch.process_packet(packet, next_port)

  def deliver_packet(self, host, packet, host_interface):
    """Deliver the packet to its final destination"""
    host.receive(host_interface, packet)

  @property
  def queued_dataplane_events(self):
    assert self.capabilities.can_queue_dp_events
    raise NotImplementedError()

  def permit_dp_event(self, dp_event):
    assert self.capabilities.can_permit_dp_event
    raise NotImplementedError()

  def drop_dp_event(self, dp_event):
    assert self.capabilities.can_drop_dp_event
    raise NotImplementedError()



class BufferedPatchPanel(DataPathBuffer, EventMixin):
  """
  A Buffered Patch panel.Listens to SwitchDPPacketOut and HostDpPacketOut
  events,  and re-raises them to listeners of this object. Does not traffic
  until given permission from a higher-level.
  """
  _eventMixin_events = set([DpPacketOut])

  def __init__(self, switches=None, hosts=None, connected_port_mapping=None,
               capabilities=None):
    if capabilities is None:
      self.capabilities = DataPathBufferCapabilities(can_queue_dp_events=True,
                                                     can_permit_dp_event=True,
                                                     can_drop_dp_event=True)
    else:
      self.capabilities = capabilities

    if switches is None:
      switches = []
    if not isinstance(switches, Iterable):
      switches = [switches]
    if hosts is None:
      hosts = []
    if not isinstance(hosts, Iterable):
      hosts = [hosts]

    self.switches = []
    self.hosts = []
    self.get_connected_port = connected_port_mapping

    # Buffered dp out events
    self.fingerprint2dp_outs = defaultdict(list)

    for switch in sorted(switches, key=lambda(sw): sw.dpid):
      self.add_switch(switch)
    for host in hosts:
      self.add_host(host)

  def _handle_DpPacketOut(self, event):
    fingerprint = (DPFingerprint.from_pkt(event.packet),
                   event.node.dpid, event.port.port_no)
    # Monkey patch on a fingerprint for this event
    event.fingerprint = fingerprint
    self.fingerprint2dp_outs[fingerprint].append(event)
    self.raiseEvent(event)

  def add_switch(self, switch):
    switch.addListener(DpPacketOut, self._handle_DpPacketOut)
    self.switches.append(switch)

  def remove_switch(self, switch):
    switch.removeListener(self._handle_DpPacketOut)
    self.switches.remove(switch)

  def add_host(self, host):
    host.addListener(DpPacketOut, self._handle_DpPacketOut)
    self.hosts.append(host)

  def remove_host(self, host):
    host.removeListener(self._handle_DpPacketOut)
    self.hosts.remove(host)

  @property
  def queued_dataplane_events(self):
    assert self.capabilities.can_queue_dp_events
    list_of_lists = self.fingerprint2dp_outs.values()
    return list(itertools.chain(*list_of_lists))

  def permit_dp_event(self, dp_event):
    """Given a SwitchDpPacketOut event, permit it to be forwarded"""
    assert self.capabilities.can_permit_dp_event
    # TODO(cs): self.forward_packet should not be externally visible!
    msg.event("Forwarding dataplane event")
    # Invoke superclass DpPacketOut handler
    self.handle_DpPacketOut(dp_event)
    self._remove_dp_event(dp_event)

  def drop_dp_event(self, dp_event):
    """
    Given a SwitchDpPacketOut event, remove it from our buffer, and do
    not forward.
    Returns the dropped event.
    """
    assert self.capabilities.can_drop_dp_event
    msg.event("Dropping dataplane event")
    self._remove_dp_event(dp_event)
    return dp_event

  def _remove_dp_event(self, dp_event):
    # Pre: dp_event.fingerprint in self.fingerprint2dp_outs
    self.fingerprint2dp_outs[dp_event.fingerprint].remove(dp_event)
    if self.fingerprint2dp_outs[dp_event.fingerprint] == []:
      del self.fingerprint2dp_outs[dp_event.fingerprint]

  def get_buffered_dp_event(self, fingerprint):
    if fingerprint in self.fingerprint2dp_outs:
      return self.fingerprint2dp_outs[fingerprint][0]
    return None


def data_path_buffer_factory(topology):
  """
  Given a pox.lib.graph.graph object with hosts, switches, and other things,
  produce an appropriate BufferedPatchPanel
  """
  return BufferedPatchPanel(
    topology.find(
      is_a=SoftwareSwitch), topology.find(is_a=HostAbstractClass),
      lambda node, port: topology.port_for_node(node, port))
