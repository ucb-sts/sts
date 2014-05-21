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
Patch panel connects the different elements in the network together.
"""


import abc

from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.entities.base import DirectedLinkAbstractClass
from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import HostInterface
from sts.entities.sts_entities import Link
from sts.util.convenience import random_eth_addr
from sts.util.console import msg


class PatchPanel(object):
  """
  Patch panel connects the different elements in the network together.

  In this basic model, the patch panel has any-to-any connectivity, but it
  can be extended to support different models. Simply all ports for each
  network element are connected to the patch panel. The patch panel can connect
  any two ports (aka create a link) or disconnect them (bring the link down),
  or migrate hosts (change the switch side of the link).

  Since this is a simple model, this class is merely a data structure to track
  link status and migrate virtual links, but it can be extended to support
  a real patch panel (OVS or hardware)

  For the simulation purposes, the PatchPanel distinguishes between links
  connecting switches to hosts (AccessLinks) and links connecting switches
  (just Link).
  """

  __metaclass__ = abc.ABCMeta

  def __init__(self, link_cls=Link, access_link_cls=AccessLink,
               port_cls=ofp_phy_port, host_interface_cls=HostInterface,
               sts_console=msg):
    super(PatchPanel, self).__init__()
    self.link_cls = link_cls
    self.access_link_cls = access_link_cls
    self.port_cls = port_cls
    self.host_interface_cls = host_interface_cls
    self.msg = sts_console

    self.cut_links = set()
    self.cut_access_links = set()
    self.dpid2switch = {}
    self.port2access_link = {}
    self.interface2access_link = {}
    self.src_port2internal_link = {}
    self.dst_port2internal_link = {}

  @property
  def network_links(self):
    """Return list of internal network links"""
    return list(set(self.src_port2internal_link.values()))

  @property
  def access_links(self):
    """Return list of access links (host->switch)"""
    return self.interface2access_link.values()

  @property
  def live_links(self):
    """Return list of live internal network links"""
    return set(self.network_links) - self.cut_links

  @property
  def live_access_links(self):
    """Return list of live access links"""
    return set(self.access_links) - self.cut_access_links

  @property
  def can_create_host_interfaces(self):
    """
    Return True if the patch panel has the ability to add new interfaces to
    hosts.
    """
    return True

  @property
  def can_create_switch_ports(self):
    """
    Return True if the patch panel has the ability to add new ports to switches.
    """
    return True

  def is_port_connected(self, port):
    """
    Return True if the port is currently connected to anything
    """
    return (port in self.port2access_link or
            port in self.interface2access_link or
            port in self.src_port2internal_link or
            port in self.dst_port2internal_link)

  def is_interface_connected(self, interface):
    """
    Return True if the interface is currently connected to anything
    """
    return interface in self.interface2access_link

  def find_unused_port(self, switch, create_new=True):
    """
    Find a switch's unused port;
    if no such port exists and create_new=True, create a new one
    """
    for _, port in switch.ports.items():
      if not self.is_port_connected(port):
        return port
    if create_new is False:
      return None
    else:
      assert self.can_create_switch_ports
    if len(switch.ports) == 0:
      new_port_number = 1
    else:
      new_port_number = max(
        [port_number for port_number in switch.ports.keys()]) + 1
    new_port = self.port_cls(hw_addr=random_eth_addr(), port_no=new_port_number)
    switch.ports[new_port_number] = new_port
    return new_port

  def find_unused_interface(self, host, create_new=True):
    """
    Find a host's unused interface;
    if no such interface exists and create_new=True, create a new one
    """
    for interface in host.interfaces:
      if not self.is_interface_connected(interface):
        return interface
    if create_new is False:
      return None
    else:
      assert self.can_create_host_interfaces
    if len(host.interfaces) == 0:
      new_port_no = 1
    else:
      new_port_no = max(
        [interface.hw_addr.toInt() for interface in host.interfaces]) + 1
    host_addr = host.hid
    host_addr = host_addr << 32
    new_interface_addr = host_addr | new_port_no
    new_interface_addr = hex(new_interface_addr)[2:].zfill(12)
    new_interface_addr = ":".join(
      new_interface_addr[i:i+2] for i in range(0, len(new_interface_addr), 2))
    new_interface = self.host_interface_cls(new_interface_addr,
                                            name="%s-eth%s" % (host.name,
                                                               new_port_no))
    host.interfaces.append(new_interface)
    return new_interface

  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          create_new_ports=True):
    """
    Create a unidirectional network (internal) link between two switches
    If a port is not provided and create_new_ports=True,
    an unused port in the corresponding switch is used.
    """
    if src_port is None:
      src_port = self.find_unused_port(src_switch, create_new_ports)
    if dst_port is None:
      dst_port = self.find_unused_port(dst_switch, create_new_ports)
    if src_port is None or dst_port is None:
      return None
    link = self.link_cls(src_switch, src_port, dst_switch, dst_port)
    self.add_link(link)
    return link

  def add_link(self, link):
    """Connect whatever necessary to make the link connected."""
    assert isinstance(link,
                      (DirectedLinkAbstractClass,
                       BiDirectionalLinkAbstractClass))
    if isinstance(link, BiDirectionalLinkAbstractClass):
      self.src_port2internal_link[link.port1] = link
      self.src_port2internal_link[link.port2] = link
      self.dst_port2internal_link[link.port1] = link
      self.dst_port2internal_link[link.port2] = link
    elif isinstance(link, DirectedLinkAbstractClass):
      self.src_port2internal_link[link.start_port] = link
      self.dst_port2internal_link[link.end_port] = link
    return link

  def remove_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          remove_all=False):
    """
    Remove a unidirectional network (internal) link(s) between two switches.

    If ports are None and remove all set to True, all links will be removed
    If ports are None and  remove all set to False and there are multiple
    links an exception will be raised.
    """
    links = []
    for port in src_switch.ports.values():
      if port in self.src_port2internal_link.keys():
        link = self.src_port2internal_link[port]
        if isinstance(link, DirectedLinkAbstractClass):
          if link.start_node is src_switch and link.end_node is dst_switch:
            if src_port is not None:
              if (link.start_port != src_port and
                      link.start_port.port_no != src_port):
                continue
            if dst_port is not None:
              if (link.end_port != dst_port and
                      link.end_port.port_no != dst_port):
                continue
        elif isinstance(link, BiDirectionalLinkAbstractClass):
          if (link.node1 == src_switch and link.node2 == dst_switch) or\
            (link.node2 == src_switch and link.node1 == dst_switch):
            if src_port is not None:
              if (link.port1 != src_port and link.port1.port_no != dst_port and
                  link.port2 != src_port and link.port2.port_no != dst_port):
                continue
        if link not in links:
          links.append(link)
    if len(links) > 1 and remove_all == False:
      raise ValueError("Multiple links connecting '%s'->'%s'" % (src_switch,
                                                                 dst_switch))
    for link in links:
      if isinstance(link, DirectedLinkAbstractClass):
        del self.src_port2internal_link[link.start_port]
        del self.dst_port2internal_link[link.end_port]
      elif isinstance(link, BiDirectionalLinkAbstractClass):
        del self.src_port2internal_link[link.port1]
        del self.src_port2internal_link[link.port2]
        del self.dst_port2internal_link[link.port1]
        del self.dst_port2internal_link[link.port2]

  def remove_access_link(self, host, interface, switch, port, remove_all=False):
    """
    Remove access link(s) between a host and a switch.

    If ports are None and remove all set to True, all links will be removed
    If ports are None and  remove all set to False and there are multiple
    links an exception will be raised.
    """
    links = []
    for iface in host.interfaces:
      if not self.is_interface_connected(iface):
        continue
      link = self.interface2access_link[iface]
      if interface is not None and iface != interface:
        continue
      if port is not None and link.switch_port != port:
        continue
      links.append(link)
    if len(links) > 1 and remove_all == False:
      raise ValueError("Multiple links connecting '%s'->'%s'" % (host,
                                                                 switch))
    for link in links:
      del self.interface2access_link[link.interface]
      del self.port2access_link[link.switch_port]

  def add_access_link(self, link):
    """Connect whatever necessary to make the link connected."""
    self.port2access_link[link.switch_port] = link
    self.interface2access_link[link.interface] = link
    return link

  def create_access_link(self, host, interface, switch, port,
                         create_new_ports=True):
    """
    Create an access link between a host and a switch
    If no interface is provided and create_new_port is False,
      an unused interface is used
    If no interface is provided and create_new_port is True and no free
      interfaces is available, a new one is created
      interfaces is available, a new one is created
    The same goes for switch ports
    """
    if interface is None:
      interface = self.find_unused_interface(host, create_new_ports)
    if port is None:
      port = self.find_unused_port(switch, create_new_ports)
    if interface is None:
      raise ValueError("Cannot find free interface at host '%s'" % host)
    if port is None:
      raise ValueError("Cannot find free port at switch '%s'" % switch)
    link = self.access_link_cls(host, interface, switch, port)
    self.add_access_link(link)
    return link

  @abc.abstractmethod
  def sever_link(self, link):
    """
    Disconnect link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()

  @abc.abstractmethod
  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_access_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()

  def remove_host(self, host):
    """
    Clean up links connected to the host when it's removed
    """
    for interface in host.interfaces:
      if interface in self.interface2access_link:
        link = self.interface2access_link[interface]
        self.remove_access_link(host, interface, link.switch, link.switch_port)

  def get_other_side(self, node, port):
    """
    Given a node and a port, return a tuple (node, port) that is directly
    connected to the port.

    This can be used in 2 ways
    - node is a Host type and port is a HostInterface type
    - node is a Switch type and port is a ofp_phy_port type.
    """
    if port in self.port2access_link:
      access_link = self.port2access_link[port]
      return access_link.host, access_link.interface
    if port in self.interface2access_link:
      access_link = self.interface2access_link[port]
      return access_link.switch, access_link.switch_port
    elif port in self.src_port2internal_link:
      network_link = self.src_port2internal_link[port]
      return network_link.end_software_switch, network_link.end_port
    else:
      raise ValueError("Unknown port %s on node %s" % (str(port), str(node)))

