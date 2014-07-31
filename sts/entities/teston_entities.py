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


import re
import logging

from pox.lib.addresses import EthAddr
from pox.lib.addresses import IPAddr

from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.hosts import HostAbstractClass
from sts.entities.hosts import HostInterface

from sts.entities.controllers import ControllerAbstractClass
from sts.entities.controllers import ControllerState


LOG = logging.getLogger("sts.entities.teston_entities")


class TestONNetworkLink(BiDirectionalLinkAbstractClass):
  def __init__(self, node1, port1, node2, port2):
    super(TestONNetworkLink, self).__init__(node1, port1, node2, port2)


class TestONAccessLink(BiDirectionalLinkAbstractClass):
  def __init__(self, host, interface, switch, switch_port):
    super(TestONAccessLink, self).__init__(host, interface, switch, switch_port)

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


class TestONHostInterface(HostInterface):
  def __init__(self, hw_addr, ips, name):
    super(TestONHostInterface, self).__init__(hw_addr, ips, name)

  @property
  def port_no(self):
    """Port number"""
    local_port_re = r'[^\-]\d\-eth(?P<port>\d+)'
    return int(re.search(local_port_re, self.name).group('port'))

  def __str__(self, *args, **kwargs):
    return self.name

  def __repr__(self):
    return "%s:%s" % (self.name, ",".join([ip.toStr() for ip in self.ips]))


class TestONHost(HostAbstractClass):
  def __init__(self, interfaces, name="", hid=None, teston_mn=None):
    super(TestONHost, self).__init__(interfaces, name, hid)
    self.teston_mn = teston_mn

  def send(self, interface, packet):
    # Mininet doesn't really deal with multiple interfaces
    pass

  def receive(self, interface, packet):
    pass

  def ping(self, host):
    ret = self.teston_mn.pingHost(SRC=self.name, TARGET=host.name)
    if ret == 1:
      return True
    else:
      return False

  def __str__(self):
    return self.name

  def __repr__(self):
    return "<Host %s: %s>" % (self.name,
                              ",".join([repr(i) for i in self.interfaces]))


class TestONOVSSwitch(object):
  def __init__(self, dpid, name, ports, can_connect_to_endhosts=False):
    self.ports = {}
    self.name = name
    self.dpid = dpid
    self.can_connect_to_endhosts = can_connect_to_endhosts
    for port in ports:
      self.ports[port.port_no] = port

  def __str__(self):
    return self.name

  def __repr__(self):
    return "<OVSSwitch %s: %s>" % (self.name,
                                   ",".join([repr(p) for p in self.ports]))


class TestONPort(object):
  def __init__(self, hw_addr, name, ips=None):
    if hw_addr:
      print "HW ADDR", hw_addr, type(hw_addr)
      hw_addr = EthAddr(hw_addr)
    self.hw_addr = hw_addr
    self.name = name
    if ips is None:
      ips = []
    if not isinstance(ips, list):
      ips = [ips]
    self.ips = []
    for ip in ips:
      self.ips.append(IPAddr(ip))

  @property
  def port_no(self):
    local_port_re = r'[^\-]\d\-eth(?P<port>\d+)'
    if self.name == 'lo':
      return 0xfffe
    return int(re.search(local_port_re, self.name).group('port'))

  def __str__(self):
    return self.name

  def __repr__(self):
    return "%s:%s" % (self.name, self.ips)


class TestONONOSConfig(object):
  """
  TestON ONOS specific configurations
  """
  def __init__(self, label, address, port,
               intent_ip=None, intent_port=None, intent_url=None):
    self.label = label
    self.address = address
    self.port = port
    self.cid = self.label
    self.intent_ip = intent_ip
    self.intent_port = intent_port
    self.intent_url = intent_url


class TestONONOSController(ControllerAbstractClass):
  """
  ONOS Controller using TestON Driver for ONOS.
  """
  def __init__(self, config, teston_onos, sync_connection_manager=None,
               snapshot_service=None, log=None):
    super(TestONONOSController, self).__init__(config,
                                               sync_connection_manager,
                                               snapshot_service)
    self.teston_onos = teston_onos
    self.log = log or LOG
    self.state = self.check_status(None)
    self._blocked_peers = set()

  @property
  def config(self):
    """Controller specific configuration object"""
    return self._config

  @property
  def label(self):
    """Human readable label for the controller"""
    return self.config.label

  @property
  def cid(self):
    """Controller unique ID"""
    return self.config.label

  @property
  def state(self):
    """
    The current controller state.

    See: ControllerState
    """
    return self._state

  @state.setter
  def state(self, value):
    self._state = value

  @property
  def snapshot_service(self):
    return self._snapshot_service

  @property
  def sync_connection_manager(self):
    return self._sync_connection_manager

  def is_remote(self):
    """
    Returns True if the controller is running on a different host that sts
    """
    return True

  def start(self, multiplex_sockets=False):
    """Starts the controller"""
    if self.state != ControllerState.DEAD:
      self.log.warn("Controller is already started!" % self.label)
      return
    self.log.info("Launching controller: %s" % self.label)
    self.teston_onos.start_all()
    self.state = ControllerState.ALIVE

  def kill(self):
    self.log.info("Killing controller: %s" % self.label)
    if self.state != ControllerState.ALIVE:
      self.log.warn("Controller already killed: %s" % self.label)
      return
    self.teston_onos.stop_all()
    self.state = ControllerState.DEAD

  def restart(self):
    """
    Restart the controller
    """
    self.log.info("Restarting controller: %s" % self.label)
    if self.state != ControllerState.DEAD:
      self.log.warn(
        "Restarting controller %s when it is not dead!" % self.label)
      return
    self.start()

  def check_status(self, simulation):
    if self.teston_onos.status() == 1:
      return ControllerState.ALIVE
    else:
      return ControllerState.DEAD

  @property
  def blocked_peers(self):
    """Return a list of blocked peer controllers (if any)"""
    return self._blocked_peers

  def block_peer(self, peer_controller):
    """Ignore traffic to/from the given peer controller
    """
    self.teston_onos.block_peer(peer_controller.config.address)
    self.blocked_peers.add(peer_controller)

  def unblock_peer(self, peer_controller):
    """Stop ignoring traffic to/from the given peer controller"""
    self.teston_onos.unblock_peer(peer_controller.config.address)
    self.blocked_peers.remove(peer_controller)

  def add_intent(self, intent):
    """
    Intent is dict with:
      intent_id
      src_dpid
      dst_dpid
      src_mac
      dst_mac
    """
    if 'intentIP' not in intent:
      intent['intentIP'] = self.config.intent_ip
    if 'intentPort' not in intent:
      intent['intentPort'] = self.config.intent_port
    if 'intentURL' not in intent:
      intent['intentURL'] = self.config.intent_url
    self.teston_onos.add_intent(**intent)

  def remove_intent(self, intent_id, intent_ip=None, intent_port=None,
                    intent_url=None):
    intent = dict(intent_id=intent_id)
    intent['intentIP'] = intent_ip or self.config.intent_ip
    intent['intentPort'] = intent_port or self.config.intent_port
    intent['intentURL'] = intent_url or self.config.intent_url
    self.teston_onos.delete_intent(**intent)

  def __repr__(self):
    return "%s (%s:%s)" % (self.label, self.config.address, self.config.port)

  def __str__(self):
    return "%s (%s:%s)" % (self.label, self.config.address, self.config.port)
