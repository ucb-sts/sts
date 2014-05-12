# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Sam Whitlock
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2012 Kyriakos Zarifis
# Copyright 2014 Ahmed El-Hassany
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
This module defines end hosts wrappers for STS.
"""

import abc
from itertools import count
import logging

from pox.openflow.software_switch import DpPacketOut
from pox.lib.revent import EventMixin
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.ipv4 import ipv4
from pox.lib.packet.tcp import tcp
from pox.lib.packet.arp import arp
from pox.lib.addresses import EthAddr
from pox.lib.addresses import IPAddr

import sts.util.network_namespace as ns
from sts.util.convenience import object_fullname
from sts.util.convenience import class_fullname
from sts.util.convenience import load_class


class HostInterfaceAbstractClass(object):
  """Represents a host's network interface (e.g. eth0)"""

  __metaclass__ = abc.ABCMeta

  def __init__(self, hw_addr, ips=None, name=""):
    self.hw_addr = hw_addr
    ips = [] if ips is None else ips
    self.ips = ips if isinstance(ips, list) else [ips]
    self.name = name

  @abc.abstractproperty
  def port_no(self):
    """Port number"""
    raise NotImplementedError()

  @abc.abstractproperty
  def _hw_addr_hash(self):
    """Hash for the HW address"""
    raise NotImplementedError()

  @abc.abstractproperty
  def _ips_hashes(self):
    """List of hashes for the IP addresses assigned to this interface"""
    raise NotImplementedError()

  def __hash__(self):
    """Generate unique hash for this interface"""
    hash_code = self._hw_addr_hash
    for ip_hash in self._ips_hashes:
      hash_code += ip_hash
    hash_code += self.name.__hash__()
    return hash_code

  def __str__(self):
    return "HostInterface:" + self.name + ":" + str(self.hw_addr) +\
           ":" + str(self.ips)

  def __repr__(self):
    return self.__str__()

  def to_json(self):
    """Serialize to JSON dict"""
    return {
            '__type__': object_fullname(self),
            'name': self.name,
            'ips': [ip.toStr() for ip in self.ips],
            'hw_addr': self.hw_addr.toStr()}

  @classmethod
  def from_json(cls, json_hash):
    """Create HostInterface Instance from JSON Dict"""
    assert class_fullname(cls) == json_hash['__type__']
    name = json_hash['name']
    ips = []
    for ip in json_hash['ips']:
      ips.append(IPAddr(str(ip)))
    hw_addr = EthAddr(json_hash['hw_addr'])
    return cls(hw_addr, ip_or_ips=ips, name=name)


class HostInterface(HostInterfaceAbstractClass):
  """ Represents a host's interface (e.g. eth0) """

  def __init__(self, hw_addr, ip_or_ips=None, name=""):
    if isinstance(hw_addr, basestring):
      hw_addr = EthAddr(hw_addr)
    ips = [] if ip_or_ips is None else ip_or_ips
    ips = ips if isinstance(ips, list) else [ips]
    for i in range(len(ips)):
      if isinstance(ips[i], basestring):
        ips[0] = IPAddr(ips[i])
    super(HostInterface, self).__init__(hw_addr, ips, name)

  @property
  def port_no(self):
    # Hack
    return self.hw_addr.toStr()

  def __eq__(self, other):
    if type(other) != HostInterface:
      return False
    if self.hw_addr.toInt() != other.hw_addr.toInt():
      return False
    other_ip_ints = [ip_addr.toUnsignedN() for ip_addr in other.ips]
    for ip_addr in self.ips:
      if ip_addr.toUnsignedN() not in other_ip_ints:
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


class HostAbstractClass(object):
  """
  Host abstract representation.
  """
  __metaclass__ = abc.ABCMeta

  _hids = count(1)

  def __init__(self, interfaces, name="", hid=None):
    """
    Init new host

    Args:
      interfaces: list of network interfaces attached to the host.
      name: human readable name of the host
      hid: unique ID for the host
    """
    interfaces = [] if interfaces is None else interfaces
    self._interfaces = interfaces
    if not isinstance(interfaces, list):
      self._interfaces = [interfaces]
    self._hid = hid if hid is not None else self._hids.next()
    self._name = name if name else "Host%s" % self._hid

  @property
  def interfaces(self):
    return self._interfaces

  @property
  def name(self):
    return self._name

  @property
  def hid(self):
    return self._hid

  @abc.abstractmethod
  def send(self, interface, packet):
    """
    Send packet on a specific interface.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def receive(self, interface, packet):
    """
    Receive a packet from a specific interface.
    """
    raise NotImplementedError()

  def has_port(self, port):
    """Return True if the port is one of the interfaces"""
    return port in self.interfaces

  def __str__(self):
    return "%s (%d)" % (self.name, self.hid)

  def __repr__(self):
    return "Host(%d)" % self.hid

  def to_json(self):
    """Serialize to JSON dict"""
    return {'__type__': object_fullname(self),
            'name': self.name,
            'hid': self.hid,
            'interfaces': [iface.to_json() for iface in self.interfaces]}

  @classmethod
  def from_json(cls, json_hash, interface_cls=None):
    name = json_hash['name']
    hid = json_hash['hid']
    interfaces = []
    for iface in json_hash['interfaces']:
      if interface_cls is None:
        interface_cls = load_class(iface['__type__'])
      else:
        iface['__type__'] = class_fullname(interface_cls)
      interfaces.append(interface_cls.from_json(iface))
    return cls(interfaces, name, hid)

#                Host
#          /      |       \
#  interface   interface  interface
#    |            |           |
# access_link acccess_link access_link
#    |            |           |
# switch_port  switch_port  switch_port

class Host(HostAbstractClass, EventMixin):
  """
  A very simple Host entity.

  For more sophisticated hosts, we should spawn a separate VM!

  If multiple host VMs are too heavy-weight for a single machine, run the
  hosts on their own machines!
  """

  _eventMixin_events = set([DpPacketOut])
  _hids = count(1)

  def __init__(self, interfaces, name="", hid=None):
    """
    Args:
      interfaces: list of network interfaces attached to the host.
      name: human readable name of the host
      hid: unique ID for the host
    """
    super(Host, self).__init__(interfaces, name, hid)
    self.log = logging.getLogger(name)
    self.send_capabilities = False

  def send(self, interface, packet):
    """Send a packet out a given interface"""
    self.log.info("sending packet on interface %s: %s" % (interface.name,
                                                          str(packet)))
    self.raiseEvent(DpPacketOut(self, packet, interface))

  def receive(self, interface, packet):
    """
    Process an incoming packet from a switch

    Called by PatchPanel
    """
    if packet.type == ethernet.ARP_TYPE:
      arp_reply = self._check_arp_reply(packet)
      if arp_reply is not None:
        self.log.info("received valid arp packet on "
                      "interface %s: %s" % (interface.name, str(packet)))
        self.send(interface, arp_reply)
        return arp_reply
      else:
        self.log.info("received invalid arp packet on "
                      "interface %s: %s" % (interface.name, str(packet)))
        return None
    elif (self.send_capabilities and packet.type == ethernet.IP_TYPE and
          packet.next.protocol == ipv4.ICMP_PROTOCOL):
      # Temporary hack: if we receive a ICMP packet, send a TCP RST to signal
      # to POX that we do want to revoke the capability for this flow. See
      # pox/pox/forwarding/capabilities_manager.py
      self.log.info("Sending RST on interface %s: in "
                    "response to: %s" % (interface.name, str(packet)))
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

    self.log.info("Received packet %s on interface "
                  "%s" % (str(packet), interface.name))

  def _check_arp_reply(self, arp_packet):
    """
    Check whether incoming packet is a valid ARP request.
    If so, construct an ARP reply and send back.
    """
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
    """
    Check if the ARP query requests any interface of this host.
    If so, return the corresponding interface.
    """
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
  """
  A host that launches a process in a separate namespace process.
  """
  def __init__(self, interfaces, create_io_worker, name="", hid=None,
               cmd="/bin/bash sleep"):
    """
    Args:
      cmd: a string of the command to execute in the separate namespace
        The default is "xterm", which opens up a new terminal window.
    """
    super(NamespaceHost, self).__init__(interfaces=interfaces, name=name,
                                        hid=hid)
    assert len(self.interfaces) == 1, ("Currently only one interface per "
                                       "host is supported")
    interface = self.interfaces[0]
    self.cmd = cmd

    (self.guest, guest_eth_addr, host_device) = ns.launch_namespace(
      cmd, interface.ips[0].toStr(), self.hid, guest_hw_addr=interface.hw_addr)

    self.socket = ns.bind_raw_socket(host_device)

    # Set up an io worker for our end of the socket
    self.io_worker = create_io_worker(self.socket)
    self.io_worker.set_receive_handler(self._io_worker_receive_handler)

    assert interface.hw_addr == EthAddr(guest_eth_addr)
    if name in ["", None]:
      self._name = "host:" + interface.ips[0].toStr()
    self.log = logging.getLogger(self.name)

  def _io_worker_receive_handler(self, io_worker):
    """
    Read a packet from the Namespace and inject it into the network.
    """
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
    """
    Send an incoming packet from a switch to the Namespace.

    Called by PatchPanel.
    """
    self.log.info("received packet on interface %s: %s. Passing to netns" %
                  (interface.name, str(packet)))
    self.io_worker.send(packet.pack())

  def to_json(self):
    """Serialize to JSON dict"""
    return {'__type__': object_fullname(self),
            'name': self.name,
            'hid': self.hid,
            'cmd': self.cmd,
            'interfaces': [iface.to_json() for iface in self.interfaces]}

  @classmethod
  def from_json(cls, json_hash, create_io_worker):
    name = json_hash['name']
    hid = json_hash['hid']
    cmd = json_hash['cmd']
    interfaces = []
    for iface in json_hash['interfaces']:
      iface_cls = load_class(iface['__type__'])
      interfaces.append(iface_cls.from_json(iface))
    return cls(interfaces, create_io_worker=create_io_worker, name=name,
               hid=hid, cmd=cmd)
