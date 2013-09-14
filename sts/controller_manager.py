# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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

''' Convenience object for encapsulating and interacting with Controller processes '''

from pox.lib.packet.ethernet import ethernet
from pox.openflow.software_switch import *
from pox.openflow.libopenflow_01 import *
from sts.entities import ControllerState
from sts.util.console import msg
import logging
log = logging.getLogger("ctrl_mgm")

class ControllerManager(object):
  ''' Encapsulate a list of controllers objects '''
  def __init__(self, controllers, simulation=None):
    self.cid2controller = {
      controller.cid : controller
      for controller in controllers
    }
    self.simulation = simulation

  def set_simulation(self, simulation):
    self.simulation = simulation

  @property
  def controller_configs(self):
    return [ c.config for c in self.controllers ]

  @property
  def controllers(self):
    cs = self.cid2controller.values()
    cs.sort(key=lambda c: c.cid)
    return cs

  @property
  def remote_controllers(self):
    # N.B. includes local controllers in network namespaces or VMs.
    return [ c for c in self.controllers if c.remote ]

  @property
  def cids(self):
    ids = self.cid2controller.keys()
    ids.sort()
    return ids

  @property
  def live_controllers(self):
    self.check_controller_status()
    alive = [controller for controller in self.controllers if controller.state == ControllerState.ALIVE]
    return set(alive)

  @property
  def down_controllers(self):
    self.check_controller_status()
    down = [controller for controller in self.controllers if controller.state == ControllerState.DEAD]
    return set(down)

  def all_controllers_down(self):
    return len(self.live_controllers) == 0

  def get_controller_by_label(self, label):
    for c in self.cid2controller.values():
      if c.label == label:
        return c
    return None

  def get_controller(self, cid):
    if cid not in self.cid2controller:
      raise ValueError("unknown cid %s" % str(cid))
    return self.cid2controller[cid]

  def kill_all(self):
    for c in self.live_controllers:
      c.kill()
    self.cid2controller = {}

  @staticmethod
  def kill_controller(controller):
    controller.kill()

  @staticmethod
  def reboot_controller(controller):
    controller.restart()

  def check_controller_status(self):
    controllers_with_problems = []
    for c in self.controllers:
      (ok, msg) = c.check_status(self.simulation)
      if ok and c.state == ControllerState.STARTING:
        c.state = ControllerState.ALIVE
      if not ok and c.state != ControllerState.STARTING:
        c.state = ControllerState.DEAD
        controllers_with_problems.append((c, msg))
    return controllers_with_problems


class ControllerPatchPanel(object):
  '''
  When multiple controllers are managing the network, we need to interpose on the
  messages sent between controllers, for at least two reasons:
    - interposition will allow us to simulate important failure modes, e.g.
      by delaying or dropping heartbeat messages.
    - interposition mitigates non-determinism during replay, as we have
      better control over message arrival.

  Note that wiring the distributed controllers to route through the
  patch panel is a separate task (specific to each controller), and is
  not implemented here. We assume here that the controllers route through
  interfaces on this machine.
  '''
  # TODO(cs): implement fingerprints for all control messages (e.g. Cassandra,
  # VRRP).
  pass

# TODO(cs): the distinction between Local/Remote may not be necessary. The
# main difference seems to be that the RemoteControllerPatchPanel must only
# use one (or two?) interfaces, and possibly tunnels, to multiplex between the
# controllers. This is in contrast to LocalControllerPatchPanel, which can
# assume an veth for each controller. It's not clear to me yet whether this difference
# is fundamental.

class LocalControllerPatchPanel(ControllerPatchPanel):
  ''' For cases when all controllers are run on this machine, either in
  virtual machines or network namepaces. '''
  def __init__(self, pass_through=True):
    # { outgoing port of our switch -> BufferedPCap bound to host veth connected to controller }
    self._port2pcap = {}
    if not pass_through:
      raise NotImplementedError("pass-through is currently the only suppported mode.")
    self.pass_through = pass_through
    # We play a clever trick to route between controllers: use a
    # SoftwareSwitch to do the switching.
    # TODO(cs): three optimization possibilities if this switch can't keep up with
    # control plane traffic or latency (measured 75ms minimum RTT on
    # localhost, with high variance):
    #   - Use OVS rather than our SoftwareSwitch. Tell OVS to automatically
    #   forward broadcast traffic (which we don't care about), and
    #   have it forward only select traffic to us. Further possibility: only simulate
    #   intermittent packet delays by telling OVS to buffer for a short period
    #   of time -- don't examine individual packets.
    #   - Don't parse the entire ethernet packets -- just do a quick lookup on
    #   the dl_dst.
    #   - Write a subclass of SoftwareSwitch that does a single hash lookup
    #   from dst EthAddr -> raw socket, without indirection through recococo
    #   events.
    self.switch = SoftwareSwitch(-1, ports=[])
    # Tell it to flood all ethernet broadcasts.
    # TODO(cs): as a (potentially substantial) optimization, act as an
    # ARP/DHCP server, since we know all addresses.
    for dl_dst in [EthAddr("FF:FF:FF:FF:FF:FF"), EthAddr("00:00:00:00:00:00")]:
      self.switch.on_message_received(None,
              ofp_flow_mod(match=ofp_match(dl_dst=dl_dst),
                           action=ofp_action_output(port=OFPP_FLOOD)))
    # Add a DpOutEvent handler.
    self.switch.addListener(DpPacketOut, self._handle_DpPacketOut)

  def _handle_DpPacketOut(self, event):
    if self.pass_through:
      # TODO(cs): log this event.
      self._port2pcap[event.port].inject(event.packet)
    # TODO(cs): implement buffering.

  def close_all_pcaps(self):
    for pcap in self.eth_addr2pcap.itervalues():
      pcap.close()

  def register_controller(self, guest_eth_addr, buffered_pcap):
    # Wire up a new port for the switch leading to this controller's pcap, and
    # tell the switch to forward any packets destined for this controller out that port.
    # The ethernet address we assign shouldn't matter afaict.
    port = ofp_phy_port(port_no=len(self.switch.ports)+1)
    self.switch.bring_port_up(port)
    self._port2pcap[port] = buffered_pcap
    self.switch.on_message_received(None,
            ofp_flow_mod(match=ofp_match(dl_dst=guest_eth_addr),
                         action=ofp_action_output(port=port)))

  def process_all_incoming_traffic(self):
    for port, pcap in self._port2pcap.iteritems():
      while not pcap.read_queue.empty():
        packet = ethernet(raw=pcap.read_queue.get())
        self.switch.process_packet(packet, port.port_no)

class RemoteControllerPatchPanel(ControllerPatchPanel):
  pass
