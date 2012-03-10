
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
from pox.lib.revent import EventMixin
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

def create_switch(switch_id, num_ports):
  ports = []
  for port_no in range(1, num_ports+1):
    port = ofp_phy_port( port_no=port_no,
                          hw_addr=EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no)) )
    # monkey patch an IP address onto the port for anteater purposes
    port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
    ports.append(port)

  def unitialized_io_worker(switch):
    raise SystemError("Not initialialized")

  return FuzzSwitchImpl(create_io_worker=unitialized_io_worker, dpid=switch_id, name="SoftSwitch(%d)" % switch_id, ports=ports)

def create_mesh(num_switches):
  ''' Returns (patch_panel, switches) '''
  
  # Every switch has a link to every other switch, for N*(N-1) total ports
  ports_per_switch = num_switches - 1

  # Initialize switches
  switches = [ create_switch(switch_id, ports_per_switch) for switch_id in range(1, num_switches+1) ]
  
  # grab a fully meshed patch panel to wire up these guys
  patch_panel = PatchPanel(switches, FullyMeshedLinks(switches).get_connected_port)

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
    def create_io_worker(switch):
      controller_socket = connect_socket_with_backoff(controller_info.address, controller_info.port)
      # Set non-blocking
      controller_socket.setblocking(0)
      return io_worker_generator(controller_socket)

    switch_impl.create_io_worker = create_io_worker
    switch_impl.connect()

def populate(controller_config_list, io_worker_constructor, num_switches=3):
  '''
  Populate the topology as a mesh of switches, connect the switches
  to the controllers, and return 
  (PatchPanel, switches, controller_sockets)
  '''
  (panel, switches) = create_mesh(num_switches)
  connect_to_controllers(controller_config_list, io_worker_constructor, switches)
  return (panel, switches)

class PatchPanel(object):
  """ A Patch panel. Contains a bunch of wires to forward packets between switches.
      Listens to the SwitchDPPacketOut event on the switches.
  """
  def __init__(self, switches, connected_port_mapping):
    '''
    Constructor.
     - switches: a list of the switches in the network
     - connected_port_mapping: a function which takes (switch_no, port_no, dpid2switch),
                               and returns the adjacent (switch, port) or None
    '''
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.get_connected_port = connected_port_mapping
    def handle_SwitchDpPacketOut(event):
      self.forward_packet(event.switch, event.packet, event.port)
    for i, s in enumerate(self.switches):
      s.addListener(SwitchDpPacketOut, handle_SwitchDpPacketOut)
  
  def forward_packet(self, switch, packet, port):
    ''' Forward the packet out the given port '''
    (switch, port) = self.get_connected_port(switch, port)
    if switch:
      switch.process_packet(packet, port.port_no)

class BufferedPatchPanel(PatchPanel, EventMixin):
  '''
  A Buffered Patch panel.Listens to the SwitchDPPacketOut event on the switches,
  and re-raises them to listeners of this object. Does not traffic until given
  permission from a higher-level.
  '''
  _eventMixin_events = set([SwitchDpPacketOut])

  def __init__(self, switches, connected_port_mapping):
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.get_connected_port = connected_port_mapping
    self.buffered_dp_out_events = set()
    def handle_SwitchDpPacketOut(event):
      self.buffered_dp_out_events.add(event)
      self.raiseEventNoErrors(event)
    for i, s in enumerate(self.switches):
      s.addListener(SwitchDpPacketOut, handle_SwitchDpPacketOut)
      
  def permit_dp_event(self, event):
    ''' Given a SwitchDpPacketOut event, permit it to be forwarded  ''' 
    # TODO: self.forward_packet should not be externally visible!
    self.forward_packet(event.switch, event.packet, event.port)
    self.buffered_dp_out_events.remove(event)
    
  def drop_dp_event(self, event):
    ''' Given a SwitchDpPacketOut event, remove it from our buffer, and do not forward ''' 
    self.buffered_dp_out_events.remove(event)
    
  def get_buffered_dp_events(self):
    ''' Return a set of all buffered SwitchDpPacketOut events ''' 
    return self.buffered_dp_out_events
     
class FullyMeshedLinks(object):
  """ A factory method for creating a fully meshed network. Connects every pair of switches. Ports are
      in ascending order of the dpid of connected switch, while skipping the self-connections.
      I.e., for (dpid, portno):
      (0, 0) <-> (1,0)
      (2, 1) <-> (1,1)
  """
  def __init__(self, switches):
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.switch_index_by_dpid = {}
    for i, s in enumerate(switches):
      self.switch_index_by_dpid[s.dpid] = i
    
  def get_connected_port(self, switch, port):
    switch_no = self.switch_index_by_dpid[switch.dpid]
    # when converting between switch and port, compensate for the skipped self port
    port_no = port.port_no - 1
    other_switch_no = port_no if port_no < switch_no else port_no + 1
    other_port_no = switch_no if switch_no < other_switch_no else switch_no - 1

    other_switch = self.switches[other_switch_no]
    return (other_switch, other_switch.ports[other_port_no+1])
