# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Sam Whitlock
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2012 Kyriakos Zarifis
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

"""
This module defines the simulated entities, such as openflow switches, links, and hosts.
"""

from pox.openflow.software_switch import DpPacketOut, OFConnection
from pox.openflow.nx_software_switch import NXSoftwareSwitch
from pox.openflow.flow_table import FlowTableModification
from pox.openflow.libopenflow_01 import *
from pox.lib.revent import EventMixin
import pox.lib.packet.ethernet as ethernet
import pox.lib.packet.ipv4 as ipv4
import pox.lib.packet.tcp as tcp
import pox.openflow.libopenflow_01 as of
from sts.openflow_buffer import OpenFlowBuffer

from sts.util.tabular import Tabular
from sts.util.network_namespace import *

from sts.entities.base import HostAbstractClass, HostInterfaceAbstractClass
from sts.entities.base import DirectedLinkAbstractClass
from sts.entities.base import BiDirectionalLinkAbstractClass


import Queue
from itertools import count
import logging
import pickle
import random
import time

class DeferredOFConnection(OFConnection):
  def __init__(self, io_worker, cid, dpid, openflow_buffer):
    super(DeferredOFConnection, self).__init__(io_worker)
    self.cid = cid
    self.dpid = dpid
    self.openflow_buffer = openflow_buffer
    # Don't feed messages to the switch directly
    self.on_message_received = self.insert_pending_receipt
    self.true_on_message_handler = None

  @property
  def closed(self):
    return self.io_worker.closed

  def get_controller_id(self):
    return self.cid

  def insert_pending_receipt(self, _, ofp_msg):
    ''' Rather than pass directly on to the switch, feed into the openflow buffer'''
    self.openflow_buffer.insert_pending_receipt(self.dpid, self.cid, ofp_msg, self)

  def set_message_handler(self, handler):
    ''' Take the switch's handler, and store it for later use '''
    self.true_on_message_handler = handler

  def allow_message_receipt(self, ofp_message):
    ''' Allow the message to actually go through to the switch '''
    self.true_on_message_handler(self, ofp_message)

  def send(self, ofp_message):
    ''' Interpose on switch sends as well '''
    self.openflow_buffer.insert_pending_send(self.dpid, self.cid, ofp_message, self)

  def allow_message_send(self, ofp_message):
    ''' Allow message actually be sent to the controller '''
    super(DeferredOFConnection, self).send(ofp_message)

class ConnectionlessOFConnection(object):
  ''' For use with InteractiveReplayer, where controllers are mocked out, and
  events are replayed to headless switches.'''
  def __init__(self, cid, dpid):
    self.cid = cid
    self.dpid = dpid
    self.on_message_received = None
    OFConnection.ID += 1
    self.ID = OFConnection.ID

  @property
  def closed(self):
    return False

  def close(self):
    pass

  def get_controller_id(self):
    return self.cid

  def set_message_handler(self, handler):
    self.on_message_handler = handler

  def send(self, ofp_message):
    ''' Into the abyss you go!'''
    pass

  # N.B. different interface than OFConnection. It's OK, since we don't actually
  # use io_workers -- this is only invoked by
  # ControlMessageReceive.manually_inject()
  def read (self, ofp_message):
    self.on_message_handler(self, ofp_message)

# A note on FuzzSoftwareSwitch Command Buffering
#   - When delaying flow_mods, we would like to buffer them and perturb the order in which they are processed.
#     self.barrier_deque is a queue of priority queues, with each priority queue representing an epoch, defined by one or two
#     barrier_in requests.
#   - When non-barrier_in flow_mods come in, they get added to the back-most (i.e. most recently added) priority queue of
#     self.barrier_deque. When a barrier_in request is received, we append that request to self.barrier_deque, together with a
#     new priority queue to buffer all subsequently received commands until all previously received commands have been processed
#     and the received barrier_in request is completed.
#   - When processing buffered commands, they are always pulled off from the front-most priority queue. If pulling off a command
#     makes the front-most queue empty, we are done with this epoch, and we can respond to the controller with a barrier_reply. We
#     then check if there is another priority queue waiting in self.barrier_deque. If there is,
#     we pop off the empty queue in front and reply to the barrier_in request that caused the creation of the next priority
#     queue. That priority queue is now at the front and is where we pull commands from.
#
# Command buffering flow chart
#   flow_mod arrived -----> insert into back-most PQ
#   barrier_in arrived ---> append (barrier_in, new PriorityQueue) to self.barrier_deque
#   flow_mod arrived -----> insert into back
# Command processing flow chart
#   get_next_command from front ---> if decide to let cmd through ---> process_delayed_command(cmd)
#                                                                 \
#                                                                  else ---> report flow mod failure
#                               ---> if front queue empty and another queue waiting ---> pop front queue off, reply to barrier_request
#                                                                                         (until the queue in front is not
#                                                                                           empty or only one queue is left)

class FuzzSoftwareSwitch (NXSoftwareSwitch):
  """
  A mock switch implementation for testing purposes. Can simulate dropping dead.
  FuzzSoftwareSwitch supports three features:
    - flow_mod delays, where flow_mods are not processed immediately
    - flow_mod processing randomization, where the order in which flow_mods are applied to the routing table perturb
    - flow_mod dropping, where flow_mods are dropped according to a given filter. This is implemented by the caller of
      get_next_command() applying a filter to the returned command and selectively allowing them through via process_next_command()

    NOTE: flow_mod processing randomization and flow_mod dropping both require flow_mod delays to be activated, but
    are not dependent on each other.
  """
  _eventMixin_events = set([DpPacketOut])

  def __init__(self, dpid, name=None, ports=4, miss_send_len=128,
               n_buffers=100, n_tables=1, capabilities=None,
               can_connect_to_endhosts=True):
    NXSoftwareSwitch.__init__(self, dpid, name, ports, miss_send_len,
                              n_buffers, n_tables, capabilities)

    # Whether this is a core or edge switch
    self.can_connect_to_endhosts = can_connect_to_endhosts
    self.create_connection = None

    self.failed = False
    self.log = logging.getLogger("FuzzSoftwareSwitch(%d)" % dpid)

    if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
      def _print_entry_remove(table_mod):
        if table_mod.removed != []:
          self.log.debug("Table entry removed %s" % str(table_mod.removed))
      self.table.addListener(FlowTableModification, _print_entry_remove)

    def error_handler(e):
      self.log.exception(e)
      raise e

    self.cid2connection = {}
    self.error_handler = error_handler
    self.controller_info = []

    # Tell our buffer to insert directly to our flow table whenever commands are let through by control_flow.
    self.delay_flow_mods = False
    self.openflow_buffer = OpenFlowBuffer()
    self.barrier_deque = None
    # Boolean representing whether to use randomize_flow_mod mode to prioritize the order in which flow_mods are processed.
    self.randomize_flow_mod_order = False
    # Uninitialized RNG (initialize through randomize_flow_mods())
    self.random = None
    self.port_violations = []

  def _output_packet(self, packet, out_port, in_port):
    try:
      return super(FuzzSoftwareSwitch, self)._output_packet(packet, out_port, in_port)
    except ValueError as e:
      self.log.warn("invalid arguments %s" % str(e))
      if type(out_port) == ofp_phy_port:
        out_port = out_port.port_no
      self.port_violations.append((self.dpid, out_port))

  def add_controller_info(self, info):
    self.controller_info.append(info)

  def _handle_ConnectionUp(self, event):
    self._setConnection(event.connection, event.ofp)

  def connect(self, create_connection, down_controller_ids=None,
              max_backoff_seconds=1024, controller_infos=None):
    ''' - create_connection is a factory method for creating Connection objects
          which are connected to controllers. Takes a ControllerConfig object
          and a reference to a switch (self) as a parameter
    '''
    if controller_infos is None:
      controller_infos = self.controller_info
    # Keep around the connection factory for fail/recovery later
    if down_controller_ids is None:
      down_controller_ids = set()
    self.create_connection = create_connection
    connected_to_at_least_one = False
    for info in controller_infos:
      # Don't connect to down controllers
      if info.cid not in down_controller_ids:
        conn = create_connection(info, self,
                                 max_backoff_seconds=max_backoff_seconds)
        self.set_connection(conn)
        # cause errors to be raised
        conn.error_handler = self.error_handler
        self.cid2connection[info.cid] = conn
        connected_to_at_least_one = True

    return connected_to_at_least_one

  def send(self, *args, **kwargs):
    if self.failed:
      self.log.warn("Currently down. Dropping send()")
    else:
      super(FuzzSoftwareSwitch, self).send(*args, **kwargs)

  def get_connection(self, cid):
    if cid not in self.cid2connection.keys():
      raise ValueError("No such connection %s" % str(cid))
    return self.cid2connection[cid]

  def is_connected_to(self, cid):
    if cid in self.cid2connection.keys():
      conn = self.get_connection(cid)
      return not conn.closed
    return False

  def fail(self):
    # TODO(cs): depending on the type of failure, a real switch failure
    # might not lead to an immediate disconnect
    if self.failed:
      self.log.warn("Switch already failed")
      return
    self.failed = True

    for connection in self.connections:
      connection.close()
    self.connections = []

  def recover(self, down_controller_ids=None):
    if not self.failed:
      self.log.warn("Switch already up")
      return
    if self.create_connection is None:
      self.log.warn("Never connected in the first place")

    # We should only ever reconnect to live controllers, so set
    # max_backoff_seconds to a low number.
    connected_to_at_least_one = self.connect(self.create_connection,
                                             down_controller_ids=down_controller_ids,
                                             max_backoff_seconds=2)
    if connected_to_at_least_one:
      self.failed = False
    return connected_to_at_least_one

  def serialize(self):
    # Skip over non-serializable data, e.g. sockets
    # TODO(cs): is self.log going to be a problem?
    serializable = FuzzSoftwareSwitch(self.dpid, self.parent_controller_name)
    # Can't serialize files
    serializable.log = None
    # TODO(cs): need a cleaner way to add in the NOM port representation
    if self.software_switch:
      serializable.ofp_phy_ports = self.software_switch.ports.values()
    return pickle.dumps(serializable, protocol=0)

  def use_delayed_commands(self):
    ''' Tell the switch to buffer flow mods '''
    self.delay_flow_mods = True
    self.on_message_received = self.on_message_received_delayed
    # barrier_deque has the structure: [(None, queue_1), (barrier_request_1, queue_2), ...] where...
    #   - its elements have the form (barrier_in_request, next_queue_to_use)
    #   - commands are always processed from the queue of the first element (i.e. barrier_deque[0][1])
    #   - when a new barrier_in request is received, a new tuple is appended to barrier_deque, containing:
    #   (<the just-received request>, <queue for subsequent non-barrier_in commands until all previous commands have been processed>)
    #   - the very first barrier_in is None because, there is no request to respond when we first start buffering commands
    self.barrier_deque = [(None, Queue.PriorityQueue())]

  def randomize_flow_mods(self, seed=None):
    ''' Initialize the RNG and tell switch to randomize order in which flow_mods
    are processed '''
    self.randomize_flow_mod_order = True
    self.random = random.Random()
    if seed is not None:
      self.random.seed(seed)

  @property
  def current_cmd_queue(self):
    ''' Alias for the current epoch's pending flow_mods. '''
    assert(len(self.barrier_deque) > 0)
    return self.barrier_deque[0][1]

  def _buffer_flow_mod(self, connection, msg, weight, buffr):
    ''' Called by on_message_received_delayed. Inserts a PendingReceive into self.openflow_buffer and sticks
    the message and receipt into the provided priority queue buffer for later retrieval. '''
    forwarder = TableInserter.instance_for_connection(connection=connection, insert_method=super(FuzzSoftwareSwitch, self).on_message_received)
    receive = self.openflow_buffer.insert_pending_receipt(self.dpid, connection.cid, msg, forwarder)
    buffr.put((weight, msg, receive))

  def on_message_received_delayed(self, connection, msg):
    ''' Precondition: use_delayed_commands() has been called. Replacement for
    NXSoftwareSwitch.on_message_received when delaying command processing '''
    # TODO(jl): use exponential moving average (define in params) rather than uniform distribution
    # to prioritize oldest flow_mods
    assert(self.delay_flow_mods)

    def choose_weight():
      ''' Return an appropriate weight to associate with a received command with when buffering. '''
      if self.randomize_flow_mod_order:
        # TODO(jl): use exponential moving average (define in params) rather than uniform distribution
        # to prioritize oldest flow_mods
        return self.random.random()
      else:
        # behave like a normal FIFO queue
        return time.time()

    def handle_with_active_barrier_in(connection, msg):
      ''' Handling of flow_mods and barriers while operating under a barrier_in request'''
      if isinstance(msg, ofp_barrier_request):
        # create a new priority queue for all subsequent flow_mods
        self.barrier_deque.append((msg, Queue.PriorityQueue()))
      elif isinstance(msg, ofp_flow_mod):
        # stick the flow_mod on the queue of commands since the last barrier request
        weight = choose_weight()
        # N.B. len(self.barrier_deque) > 1, because an active barrier_in implies we appended a queue to barrier_deque, which
        # already always has at least one element: the default queue
        self._buffer_flow_mod(connection, msg, weight, buffr=self.barrier_deque[-1][1])
      else:
        raise TypeError("Unsupported type for command buffering")

    def handle_without_active_barrier_in(connection, msg):
      if isinstance(msg, ofp_barrier_request):
        if self.current_cmd_queue.empty():
          # if no commands waiting, reply to barrier immediately
          self.log.debug("Barrier request %s %s", self.name, str(msg))
          barrier_reply = ofp_barrier_reply(xid = msg.xid)
          self.send(barrier_reply)
        else:
          self.barrier_deque.append((msg, Queue.PriorityQueue()))
      elif isinstance(msg, ofp_flow_mod):
        # proceed normally (no active or pending barriers)
        weight = choose_weight()
        self._buffer_flow_mod(connection, msg, weight, buffr=self.current_cmd_queue)
      else:
        raise TypeError("Unsupported type for command buffering")

    if isinstance(msg, ofp_flow_mod) or isinstance(msg, ofp_barrier_request):
      # Check if switch is currently operating under a barrier request
      # Note that we start out with len(self.barrier_deque) == 1, add an element for each barrier_in request, and never
      # delete when len(self.barrier_deque) == 1
      if len(self.barrier_deque) > 1:
        handle_with_active_barrier_in(connection, msg)
      else:
        handle_without_active_barrier_in(connection, msg)
    else:
      # Immediately process all other messages
      super(FuzzSoftwareSwitch, self).on_message_received(connection, msg)

  def has_pending_commands(self):
    return not self.current_cmd_queue.empty()

  def get_next_command(self):
    """ Precondition: use_delayed_commands() has been invoked. Invoked periodically from fuzzer.
    Retrieves the next buffered command and its PendingReceive receipt. Throws Queue.Empty if
    the queue is empty. """
    assert(self.delay_flow_mods)
    # tuples in barrier are of the form (weight, buffered command, pending receipt)
    (buffered_cmd, buffered_cmd_receipt) = self.current_cmd_queue.get_nowait()[1:]
    while self.current_cmd_queue.empty() and len(self.barrier_deque) > 1:
      # It's time to move to the next epoch and reply to the most recent barrier_request.
      # barrier_deque has the structure: [(None, queue_1), (barrier_request_1, queue_2), ...]
      # so when we empty queue_x, we just finished processing and thus must reply to barrier_request_x, which is coupled in
      # the next element in barrier_deque: (barrier_request_x, queue_x+1)
      self.barrier_deque.pop(0)
      finished_barrier_request = self.barrier_deque[0][0]
      if finished_barrier_request:
        self.log.debug("Barrier request %s %s", self.name, str(finished_barrier_request))
        barrier_reply = ofp_barrier_reply(xid = finished_barrier_request.xid)
        self.send(barrier_reply)
    return (buffered_cmd, buffered_cmd_receipt)

  def process_delayed_command(self, buffered_cmd_receipt):
    """ Precondition: use_delayed_commands() has been invoked and buffered_cmd_receipt is the PendingReceive
    for a previously received and buffered command (i.e. was returned by get_next_command()) Returns the
    original buffered command """
    assert(self.delay_flow_mods)
    return self.openflow_buffer.schedule(buffered_cmd_receipt)

  def show_flow_table(self):
    dl_types = { 0x0800: "IP",
                 0x0806: "ARP",
                 0x8100: "VLAN",
                 0x88cc: "LLDP",
                 0x888e: "PAE"
                 }
    nw_protos = { 1 : "ICMP", 6 : "TCP", 17 : "UDP" }

    ports = { v: k.replace("OFPP_","") for (k,v) in of.ofp_port_rev_map.iteritems() }

    def dl_type(e):
      d = e.match.dl_type
      if d is None:
        return d
      else:
        return dl_types[d] if d in dl_types else "%x" %d

    def nw_proto(e):
      p = e.match.nw_proto
      return nw_protos[p] if p in nw_protos else p

    def action(a):
      if isinstance(a, ofp_action_output):
        return ports[a.port] if a.port in ports else "output(%d)" % a.port
      else:
        return str(a)
    def actions(e):
      if len(e.actions) == 0:
        return "(drop)"
      else:
        return ", ".join(action(a) for a in e.actions)

    t = Tabular((("Prio", lambda e: e.priority),
                 ("in_port", lambda e: e.match.in_port),
                 ("dl_type", dl_type),
                 ("dl_src", lambda e: e.match.dl_src),
                 ("dl_dst", lambda e: e.match.dl_dst),
                 ("nw_proto", nw_proto),
                 ("nw_src", lambda e: e.match.nw_src),
                 ("nw_dst", lambda e: e.match.nw_dst),
                 ("tp_src", lambda e: e.match.tp_src),
                 ("tp_dst", lambda e: e.match.tp_dst),
                 ("actions", actions),
                ))
    t.show(self.table.entries)

class Link (DirectedLinkAbstractClass):
  """
  A network link between two switches

  Temporary stand in for Murphy's graph-library for the NOM.

  Note: Directed!
  """
  def __init__(self, start_software_switch, start_port,
               end_software_switch, end_port):
    if type(start_port) == int:
      assert(start_port in start_software_switch.ports)
      start_port = start_software_switch.ports[start_port]
    if type(end_port) == int:
      assert(end_port in start_software_switch.ports)
      end_port = end_software_switch.ports[end_port]
    super(Link, self).__init__(start_software_switch, start_port,
                               end_software_switch, end_port)
    assert_type("start_port", start_port, ofp_phy_port, none_ok=False)
    assert_type("end_port", end_port, ofp_phy_port, none_ok=False)
    self.start_software_switch = start_software_switch
    self.end_software_switch = end_software_switch

  def __eq__(self, other):
    if not type(other) == Link:
      return False
    ret = (self.start_software_switch.dpid == other.start_software_switch.dpid and
            self.start_port.port_no == other.start_port.port_no and
            self.end_software_switch.dpid == other.end_software_switch.dpid and
            self.end_port.port_no == other.end_port.port_no)
    return ret

  def __ne__(self, other):
    # NOTE: __ne__ in python does *NOT* by default delegate to eq
    return not self.__eq__(other)


  def __hash__(self):
    return (self.start_software_switch.dpid.__hash__() +  self.start_port.port_no.__hash__() +
           self.end_software_switch.dpid.__hash__() +  self.end_port.port_no.__hash__())

  def __repr__(self):
    return "(%d:%d) -> (%d:%d)" % (self.start_software_switch.dpid, self.start_port.port_no,
                                   self.end_software_switch.dpid, self.end_port.port_no)

  def reversed_link(self):
    '''Create a Link that is in the opposite direction of this Link.'''
    return Link(self.end_software_switch, self.end_port,
                self.start_software_switch, self.start_port)

class AccessLink (BiDirectionalLinkAbstractClass):
  '''
  Represents a bidirectional edge: host <-> ingress switch
  '''
  def __init__(self, host, interface, switch, switch_port):
    super(AccessLink, self).__init__(host, interface, switch, switch_port)
    assert_type("interface", interface, HostInterface, none_ok=False)
    assert_type("switch_port", switch_port, ofp_phy_port, none_ok=False)

  @property
  def host(self):
    return self.node1

  @property
  def interface(self):
    return self.port1

  @property
  def switch(self):
    return self.node2

  @property
  def switch_port(self):
    return self.port2


class HostInterface (HostInterfaceAbstractClass):
  """ Represents a host's interface (e.g. eth0) """

  def __init__(self, hw_addr, ip_or_ips=[], name=""):
    super(HostInterface, self).__init__(hw_addr, ip_or_ips, name)

  @property
  def port_no(self):
    # Hack
    return self.hw_addr.toStr()

  def __eq__(self, other):
    if type(other) != HostInterface:
      return False
    if self.hw_addr.toInt() != other.hw_addr.toInt():
      return False
    other_ip_ints = map(lambda ip: ip.toUnsignedN(), other.ips)
    for ip in self.ips:
      if ip.toUnsignedN() not in other_ip_ints:
        return False
    if len(other.ips) != len(self.ips):
      return False
    if self.name != other.name:
      return False
    return True

  @property
  def _ips_hashes(self):
    hashes = [ip.toUnsignedN().__hash__() for ip in self.ips]
    return hashes

  @property
  def _hw_addr_hash(self):
    return self.hw_addr.toInt().__hash__()

  def __str__(self, *args, **kwargs):
    return "HostInterface:" + self.name + ":" + \
           str(self.hw_addr) + ":" + str(self.ips)

  def __repr__(self, *args, **kwargs):
    return self.__str__()

  def to_json(self):
    return {'name' : self.name,
            'ips' : [ ip.toStr() for ip in self.ips ],
            'hw_addr' : self.hw_addr.toStr()}

  @staticmethod
  def from_json(json_hash):
    name = json_hash['name']
    ips = []
    for ip in json_hash['ips']:
      ips.append(IPAddr(str(ip)))
    hw_addr = EthAddr(json_hash['hw_addr'])
    return HostInterface(hw_addr, ip_or_ips=ips, name=name)

#                Host
#          /      |       \
#  interface   interface  interface
#    |            |           |
# access_link acccess_link access_link
#    |            |           |
# switch_port  switch_port  switch_port

class Host (EventMixin, HostAbstractClass):
  '''
  A very simple Host entity.

  For more sophisticated hosts, we should spawn a separate VM!

  If multiple host VMs are too heavy-weight for a single machine, run the
  hosts on their own machines!
  '''

  _eventMixin_events = set([DpPacketOut])
  _hids = count(1)

  def __init__(self, interfaces, name=""):
    '''
    - interfaces A list of HostInterfaces
    '''
    HostAbstractClass.__init__(self, interfaces, name)
    self.log = logging.getLogger(name)
    self.send_capabilities = False

  def send(self, interface, packet):
    ''' Send a packet out a given interface '''
    self.log.info("sending packet on interface %s: %s" % (interface.name, str(packet)))
    self.raiseEvent(DpPacketOut(self, packet, interface))

  def receive(self, interface, packet):
    '''
    Process an incoming packet from a switch

    Called by PatchPanel
    '''
    if packet.type == ethernet.ARP_TYPE:
      arp_reply = self._check_arp_reply(packet)
      if arp_reply is not None:
        self.log.info("received valid arp packet on interface %s: %s" % (interface.name, str(packet)))
        self.send(interface, arp_reply)
        return arp_reply
      else:
        self.log.info("received invalid arp packet on interface %s: %s" % (interface.name, str(packet)))
        return None
    elif self.send_capabilities and packet.type == ethernet.IP_TYPE and packet.next.protocol == ipv4.ICMP_PROTOCOL:
      # Temporary hack: if we receive a ICMP packet, send a TCP RST to signal to POX
      # that we do want to revoke the capability for this flow. See
      # pox/pox/forwarding/capabilities_manager.py
      self.log.info("Sending RST on interface %s: in reponse to: %s" % (interface.name, str(packet)))
      t = tcp()
      tcp.RST = True
      i = ipv4()
      i.protocol = ipv4.TCP_PROTOCOL
      i.srcip = interface.ips[0]
      i.dstip = packet.next.srcip
      i.payload = t
      ether = ethernet()
      ether.type = ethernet.IP_TYPE
      ether.src = interface.hw_addr
      ether.dst = packet.src
      ether.payload = i
      self.send(interface, ether)

    self.log.info("Recieved packet %s on interface %s" % (str(packet), interface.name))

  def _check_arp_reply(self, arp_packet):
    '''
    Check whether incoming packet is a valid ARP request. If so, construct an ARP reply and send back
    '''
    arp_packet_payload = arp_packet.payload
    if arp_packet_payload.opcode == arp.REQUEST:
      interface_matched = self._if_valid_arp_request(arp_packet_payload)
      if interface_matched is None:
        return None
      else:
        # This ARP query is for this host, construct an reply packet
        arp_reply = arp()
        arp_reply.hwsrc = interface_matched.hw_addr
        arp_reply.hwdst = arp_packet_payload.hwsrc
        arp_reply.opcode = arp.REPLY
        arp_reply.protosrc = arp_packet_payload.protodst
        arp_reply.protodst = arp_packet_payload.protosrc
        ether = ethernet()
        ether.type = ethernet.ARP_TYPE
        ether.src = interface_matched.hw_addr
        ether.dst = arp_packet.src
        ether.payload = arp_reply
        return ether

  def _if_valid_arp_request(self, arp_request_payload):
    '''
    Check if the ARP query requests any interface of this host. If so, return the corresponding interface.
    '''
    for interface in self.interfaces:
      if arp_request_payload.protodst in interface.ips:
        return interface
    return None

  @property
  def dpid(self):
    # Hack
    return self.hid

  def __str__(self):
    return "%s (%d)" % (self.name, self.hid)

  def __repr__(self):
    return "Host(%d)" % self.hid

class NamespaceHost(Host):
  '''
  A host that launches a process in a separate namespace process.
  '''
  def __init__(self, ip_addr_str, create_io_worker, name="", cmd="/bin/bash sleep"):
    '''
    - ip_addr_str must be a string! not a IPAddr object
    - cmd: a string of the command to execute in the separate namespace
      The default is "xterm", which opens up a new terminal window.
    '''
    self.hid = self._hids.next()
    (self.guest, guest_eth_addr, host_device) = launch_namespace(cmd, ip_addr_str, self.hid)
    self.socket = bind_raw_socket(host_device)
    # Set up an io worker for our end of the socket
    self.io_worker = create_io_worker(self.socket)
    self.io_worker.set_receive_handler(self._io_worker_receive_handler)

    self.interfaces = [HostInterface(guest_eth_addr, IPAddr(ip_addr_str))]
    if name == "":
      name = "host:" + ip_addr_str
    self.name = name
    self.log = logging.getLogger(name)

  def _io_worker_receive_handler(self, io_worker):
    '''
    Read a packet from the Namespace and inject it into the network.
    '''
    message = io_worker.peek_receive_buf()
    # Create an ethernet packet
    # TODO(cs): this assumes that the raw socket returns exactly one ethernet
    # packet. Since ethernet frames do not include length information, the
    # only way to correctly handle partial packets would be to get access to
    # framing information. Should probably look at what Mininet does.
    packet = ethernet(raw=message)
    if not packet.parsed:
      return
    io_worker.consume_receive_buf(packet.hdr_len + packet.payload_len)
    self.log.info("received packet from netns %s: " % str(packet))
    super(NamespaceHost, self).send(self.interfaces[0], packet)

  def receive(self, interface, packet):
    '''
    Send an incoming packet from a switch to the Namespace.

    Called by PatchPanel.
    '''
    self.log.info("received packet on interface %s: %s. Passing to netns" %
                  (interface.name, str(packet)))
    self.io_worker.send(packet.pack())


class SnapshotPopen(object):
  ''' Popen wrapper for processes that were not created by us. '''
  def __init__(self, pid):
    import psutil
    # See https://code.google.com/p/psutil/wiki/Documentation
    # for the full API.
    self.p = psutil.Process(pid)
    self.log = logging.getLogger("c%d" % pid)

  def poll(self):
    ''' A None value indicates that the process hasn't terminated yet. '''
    if self.p.is_running():
      return None
    else:
      return 1

  @property
  def pid(self):
    return self.p.pid

  def kill(self):
    import psutil
    self.log.info("Killing controller process %d" % self.pid)
    try:
      return self.p.kill()
    except psutil._error.NoSuchProcess:
      self.log.info("controller process %d already dead?" % self.pid)
      return None # Already dead

  def terminate(self):
    import psutil
    self.log.info("Terminating controller process %d" % self.pid)
    try:
      return self.p.terminate()
    except psutil._error.NoSuchProcess:
      self.log.info("controller process %d already dead?" % self.pid)
      return None # Already dead


class TableInserter(object):
  ''' Shim layer sitting between incoming messages and a switch. This class is duck-typed to offer the same
  (received message) API to OpenFlowBuffer as a DeferredOFConnection. Instances of this class should be created and
  retrieved by providing TableInserter.instance_for_connection() with a method to insert a flow_mod directly into
  a switch's table and the connection the flow_mod came in on. Each switch should create and use one TableInserter
  for each connection it receives a flow_mod from.
  '''
  connection2instance = {}

  @staticmethod
  def instance_for_connection(connection, insert_method):
    ''' Instantiates or retrieves the TableInserter for the given connection for the switch '''
    if connection.ID not in TableInserter.connection2instance:
      # Note: may cause memory leak if new connections w/ new connection.ID's are constanty created and not reused
      TableInserter.connection2instance[connection.ID] = TableInserter(connection, insert_method)
    return TableInserter.connection2instance[connection.ID]

  def __init__(self, connection, insert_method):
    self.connection = connection
    self.insert_method = insert_method

  def allow_message_receipt(self, message):
    return self.insert_method(self.connection, message)

