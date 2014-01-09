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

from pox.lib.util import connect_socket_with_backoff
from pox.lib.packet.ethernet import ethernet
from pox.lib.ioworker.io_worker import JSONIOWorker
from pox.openflow.software_switch import *
from pox.openflow.libopenflow_01 import *
from sts.entities import ControllerState
from sts.util.console import msg
from sts.util.network_namespace import bind_raw_socket
from sts.util.convenience import base64_encode
from sts.entities import ConnectionlessOFConnection

import subprocess
import os
import abc
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
    ''' Note! you must invoke check_controller_status if you want an
    up-to-date list of the live controllers'''
    alive = [controller for controller in self.controllers if controller.state == ControllerState.ALIVE]
    return set(alive)

  @property
  def down_controllers(self):
    ''' Note! you must invoke check_controller_status if you want an
    up-to-date list of the down controllers'''
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
    ''' N.B. this method mutates the state of the controller objects '''
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
  (virtual) interfaces on this machine, one for each controller.
  '''
  __metaclass__ = abc.ABCMeta

  # TODO(cs): implement fingerprints for all control messages (e.g. Cassandra,
  # VRRP).
  def __init__(self, create_io_worker):
    self.create_io_worker = create_io_worker
    # { cid of connected controller -> ethernet address }
    self._cid2ethaddr = {}

  def _initialize_switch(self):
    # Tell it to flood all ethernet broadcasts.
    # TODO(cs): as a (potentially substantial) optimization, act as an
    # ARP/DHCP server, since we know all addresses.
    for dl_dst in [EthAddr("FF:FF:FF:FF:FF:FF"), EthAddr("00:00:00:00:00:00")]:
      self._send_command(ofp_flow_mod(match=ofp_match(dl_dst=dl_dst),
                                     action=ofp_action_output(port=OFPP_FLOOD)))
    # Tell it to drop all unmatched packets.
    self._send_command(ofp_flow_mod(match=ofp_match(), priority=1))

  @abc.abstractmethod
  def _send_command(self, command):
    pass

  def register_controller(self, cid, guest_eth_addr, host_device):
    ''' Register a controller with this patch panel.'''
    self._cid2ethaddr[cid] = guest_eth_addr
    # Create a port for this controller.
    port = self._create_port_for_controller(guest_eth_addr, host_device)
    # Tell the switch to forward any packets destined for this controller out that port.
    self._send_command(ofp_flow_mod(match=ofp_match(dl_dst=guest_eth_addr),
                                   action=ofp_action_output(port=port)))

  @abc.abstractmethod
  def _create_port_for_controller(self):
    pass

  def clean_up(self):
    pass

  def block_controller_pair(self, cid1, cid2):
    ''' Drop all messages sent between controller 1 and controller 2 until
    unblock_controller_pair is called. '''
    ethaddr1 = self._cid2ethaddr[cid1]
    ethaddr2 = self._cid2ethaddr[cid2]
    # Make sure to block both directions.
    # TODO(cs): support unidirectional blocks.
    # N.B. no actions implies drop.
    self._send_command(ofp_flow_mod(match=ofp_match(dl_dst=ethaddr1,dl_src=ethaddr2),
                                    priority=OFP_DEFAULT_PRIORITY+1))
    self._send_command(ofp_flow_mod(match=ofp_match(dl_dst=ethaddr2,dl_src=ethaddr1),
                                    priority=OFP_DEFAULT_PRIORITY+1))

  def unblock_controller_pair(self, cid1, cid2):
    ''' Stop dropping messages sent between controller 1 and controller 2 '''
    ethaddr1 = self._cid2ethaddr[cid1]
    ethaddr2 = self._cid2ethaddr[cid2]
    self._send_command(ofp_flow_mod(match=ofp_match(dl_dst=ethaddr1,dl_src=ethaddr2),
                                    priority=OFP_DEFAULT_PRIORITY+1,
                                    command=OFPFC_DELETE))
    self._send_command(ofp_flow_mod(match=ofp_match(dl_dst=ethaddr2,dl_src=ethaddr1),
                                    priority=OFP_DEFAULT_PRIORITY+1,
                                    command=OFPFC_DELETE))


class UserSpaceControllerPatchPanel(ControllerPatchPanel):
  ''' Uses a python SoftwareSwitch to route between controllers.'''
  def __init__(self, create_io_worker):
    super(UserSpaceControllerPatchPanel, self).__init__(create_io_worker)
    # We play a clever trick to route between controllers: use a
    # SoftwareSwitch to do the switching.
    # TODO(cs): three optimization possibilities if this switch can't keep up with
    # control plane traffic or latency (measured 75ms minimum RTT on
    # localhost, with high variance):
    #   - Use OVS rather than our SoftwareSwitch. Tell OVS to automatically
    #   forward broadcast traffic (which we don't care about), and
    #   have it forward only select traffic to us. Further possibility: write a
    #   separate click or custom C program to control OVS, that talks back to
    #   this python process via RPC.
    #   - Don't parse the entire ethernet packets -- just do a quick lookup on
    #   the dl_dst.
    #   - Write a subclass of SoftwareSwitch that does a single hash lookup
    #   from dst EthAddr -> raw socket, without indirection through recococo
    #   events.
    self.switch = SoftwareSwitch(-1, ports=[])
    # { outgoing port of our switch -> io_worker bound to host veth connected to controller }
    self._port2io_worker = {}
    # Add a DpOutEvent handler.
    # TODO(cs): potential optimization: don't redirect through revent;
    # have the switch directly output the pcap.
    self.switch.addListener(DpPacketOut,
            lambda event: self._port2io_worker[event.port].send(event.packet.pack()))
    self._initialize_switch()

  def clean_up(self):
    for io_worker in self._port2io_worker.itervalues():
      io_worker.close()

  def _send_command(self, command):
    self.switch.on_message_received(None, command)

  def _create_port_for_controller(self, guest_eth_addr, host_device):
    # Wire up a new port for the switch leading to this controller's io_worker, and
    # The ethernet address we assign to the switch's port shouldn't matter afaict.
    port = ofp_phy_port(port_no=len(self.switch.ports)+1)
    self.switch.bring_port_up(port)

    # Hook up a raw_socket and io_worker for this host_device.
    # TODO(cs): suport pcap filtering as an alternative to raw sockets. Would
    # require us to modify pxpcap to allow us to wrap a non-blocking pcap in
    # an io_worker.
    raw_socket = bind_raw_socket(host_device)
    # Set up an io worker for our end of the socket, and tell it to
    # immediately send packets to the switch.
    # TODO(cs): create_io_worker is a broken reference!
    io_worker = self.create_io_worker(raw_socket)
    # TODO(cs): not sure if this line is strictly needed for the closure.
    switch = self.switch
    def _process_raw_socket_read(io_worker):
      # N.B. raw sockets return exactly one ethernet frame for every read().
      data = io_worker.peek_receive_buf()
      packet = ethernet(bytes(data))
      io_worker.consume_receive_buf(len(data))
      if log.isEnabledFor(logging.DEBUG):
        log.debug("Dequeing packet %s, port %s" % (packet, port))
      switch.process_packet(packet, port.port_no)
    io_worker.set_receive_handler(_process_raw_socket_read)
    self._port2io_worker[port] = io_worker
    return port

class OVSControllerPatchPanel(ControllerPatchPanel):
  ''' Uses OVS to route between controllers. '''
  of_port = 8765
  messenger_port = 9876

  def __init__(self, create_io_worker):
    super(OVSControllerPatchPanel, self).__init__(create_io_worker)
    # Boot up POX.
    args = str("""./pox.py openflow.of_01 --address=127.0.0.1 --port=%d"""
               """         messenger.messenger --tcp_address=127.0.0.1 --tcp_port=%d """
               """         sts_of_forwarder.sts_of_forwarder """ %
               (self.of_port, self.messenger_port)).split()
    self.pox = subprocess.Popen(args, cwd="./pox/", preexec_fn=lambda: os.setsid())
    # Establish connection with POX messenger component.
    true_socket = connect_socket_with_backoff(address="127.0.0.1",
                                              port=self.messenger_port)
    self.json_worker = JSONIOWorker(create_io_worker(true_socket))
    # Send the handshake.
    self.json_worker.send({"sts_connection": ""})
    self._initialize_switch()

  def _send_command(self, command):
    b64_pkt = base64_encode(command)
    self.json_worker.send(b64_pkt)

  def _create_port_for_controller(self, guest_eth_addr, host_device):
    raise NotImplementedError("")

  def clean_up(self):
    self.json_worker.close()
    self.pox.kill()

# --- The following mock methods are for use by interactive_replay.py and openflow_replayer.py,
# who do not necessarily want to replay with true controller instances ---

class MockControllerManager(object):
  def __init__(self, controller_configs):
    self.controller_configs = controller_configs
  def set_simulation(self, simulation): pass
  def kill_all(self): pass
  # TODO(cs): these properties are only a temporary fix. In the long run, we
  # should refactor interactive_replayer to use its own help options, distinct
  # from interactive's help options.
  @property
  def live_controllers(self): return []
  @property
  def down_controllers(self): return []
  def check_controller_status(self): return []
  def all_controllers_down(self): return False

def boot_mock_controllers(controller_configs, snapshot_service,
                          sync_connection_manager, multiplex_sockets=False):
  return MockControllerManager(controller_configs)

def create_mock_connection(controller_config, software_switch, max_backoff_seconds=1024):
  return ConnectionlessOFConnection(controller_config.cid, software_switch.dpid)

def connect_to_mock_controllers(simulation):
  simulation.topology.connect_to_controllers(simulation.controller_manager.controller_configs,
                                             create_connection=create_mock_connection)

