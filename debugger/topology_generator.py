
# Nom nom nom nom

'''
If the user does not specify a topology to test on, use by default a full mesh
of switches. For example, with N = 3:

              controller

     switch1-(1)------------(3)--switch2
        \                       /
        (2)                   (4)
          \                   /
           \                 /
            \               /
             (6)-switch3-(5)

TODO: should this topology include Hosts as well?
'''

from debugger_entities import FuzzSwitchImpl
from pox.openflow.switch_impl import ofp_phy_port, EthAddr, SwitchDpPacketOut
from pox.lib.util import connect_socket_with_backoff
import socket
import time
import errno
import sys

class Cycler():
  """
  Abstraction for cycling through the given list circularly:

  c = Cycler([1,2,3])
  while True:
    print c.next()
  """
  def __init__(self, arr):
    self._list = list(arr)
    self._current_index = 0

  def next(self):
    if len(self._list) == 0:
      return None

    element = self._list[self._current_index]
    self._current_index += 1
    self._current_index %= len(self._list)
    return element

def create_switch(io_worker_constructor, io_worker_destructor, switch_id, num_ports):
  ports = []
  for port_no in range(1, num_ports+1):
    port = ofp_phy_port( port_no=port_no,
                          hw_addr=EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no)) )
    # monkey patch an IP address onto the port for anteater purposes
    port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
    ports.append(port)

  return FuzzSwitchImpl(io_worker_constructor, io_worker_destructor, dpid=switch_id, name="SoftSwitch(%d)" % switch_id, ports=ports)

def create_mesh(num_switches, io_worker_constructor, io_worker_destructor):
  ''' Returns (patch_panel, switches) '''
  
  # Every switch has a link to every other switch, for N*(N-1) total ports
  ports_per_switch = num_switches - 1

  # Initialize switches
  switches = [ create_switch(io_worker_constructor, io_worker_destructor, switch_id, ports_per_switch) for switch_id in range(1, num_switches+1) ]

  # grab a fully meshed patch panel to wire up these guys
  patch_panel = FullyMeshedPanel(switches)

  return (patch_panel, switches)

def connect_to_controllers(controller_info_list, io_worker_generator, switch_impls):
  '''
  Bind sockets from the switch_impls to the controllers. For now, assign each switch to the next
  controller in the list in a round robin fashion.
  
  Controller info list is a list of (controller ip address, controller port number) tuples
  
  Return a list of socket objects
  '''
  controller_info_cycler = Cycler(controller_info_list)
  
  for switch_impl in switch_impls:
    # TODO: what if the controller is slow to boot?
    # Socket from the switch_impl to the controller
    controller_info = controller_info_cycler.next()
    controller_socket = connect_socket_with_backoff(controller_info.address, controller_info.port)
    # Set non-blocking
    controller_socket.setblocking(0)
    io_worker = io_worker_generator(controller_socket)
    switch_impl.set_socket(io_worker)

def populate(controller_config_list, io_worker_constructor, io_worker_destructor, num_switches=3):
  '''
  Populate the topology as a mesh of switches, connect the switches
  to the controllers, and return 
  (PatchPanel, switches, controller_sockets)
  '''
  (panel, switches) = create_mesh(num_switches, io_worker_constructor, io_worker_destructor)
  connect_to_controllers(controller_config_list, io_worker_constructor, switches)
  return (panel, switches)

class PatchPanel(object):
  """ A Patch panel. Contains a bunch of wires to forward packets between switches.
      Listens to the SwitchDPPacketOut event on the switches.
      Implement connected_port in subclasses to define the concrete wiring.
  """
  def __init__(self, switches):
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.switch_index_by_dpid = {}
    def handle_SwitchDpPacketOut(event):
      self.forward_packet(event.switch, event.packet, event.port)

    for i, s in enumerate(self.switches):
      s.addListener(SwitchDpPacketOut, handle_SwitchDpPacketOut)
      self.switch_index_by_dpid[s.dpid] = i

  def forward_packet(self, switch, packet, port):
    (switch, port) = self.connected_port(switch, port)
    if switch:
      switch.process_packet(packet, port.port_no)

  def connected_port(self, switch, port):
    """ return (switch: SwitchImpl, port: ofp_phy_port) connected to this switch """
    raise SystemError("Please implement forward_packet")

class FullyMeshedPanel(PatchPanel):
  """ A fully meshed patch panel. Connects every pair of switches. Ports are
      in ascending order of the dpid of connected switch, while skipping the self-connections.
      I.e., for (dpid, portno):
      (0, 0) <-> (1,0)
      (2, 1) <-> (1,1)
  """
  def connected_port(self, switch, port):
    switch_no = self.switch_index_by_dpid[switch.dpid]
    port_no   = port.port_no - 1

    # when converting between switch and port, compensate for the skipped self port
    other_switch_no = port_no if port_no < switch_no else port_no + 1
    other_port_no = switch_no if switch_no < other_switch_no else switch_no - 1

    other_switch = self.switches[other_switch_no]
    return (other_switch, other_switch.ports[other_port_no+1])
