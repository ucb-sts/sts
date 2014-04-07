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


from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.hosts import HostAbstractClass
from sts.entities.hosts import HostInterface


class MininetLink(BiDirectionalLinkAbstractClass):
  def __init__(self, node1, port1, node2, port2):
    super(MininetLink, self).__init__(node1, port1, node2, port2)


class MininetAccessLink(BiDirectionalLinkAbstractClass):
  def __init__(self, host, interface, switch, switch_port):
    super(MininetAccessLink, self).__init__(host, interface, switch, switch_port)

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


class MininetHostInterface(HostInterface):
  def __init__(self, hw_addr, ips, name):
    super(MininetHostInterface, self).__init__(hw_addr, ips, name)

  def __repr__(self):
    return "%s:%s" % (self.name, ",".join([ip.toStr() for ip in self.ips]))


class MininetHost(HostAbstractClass):
  def __init__(self, interfaces, name="", hid=None):
    super(MininetHost, self).__init__(interfaces, name, hid)

  def send(self, interface, packet):
    # Mininet doesn't really deal with multiple interfaces
    pass

  def receive(self, interface, packet):
    pass

  def __repr__(self):
    return "<Host " + self.name + ": " + ",".join([repr(i) for i in self.interfaces]) + ">"


class MininetOVSSwitch(object):
  def __init__(self, dpid, name, ports):
    self.ports = ports
    self.name = name
    self.dpid = dpid

  def __str__(self):
    return self.name

  def __repr__(self):
    return "<OVSSwitch " + self.name + ": " + ",".join([repr(p) for p in self.ports]) + ">"


class MininetPort(object):
  def __init__(self, hw_addr, name, ips=None):
    self.hw_addr = hw_addr
    self.name = name
    self.ips = ips

  def __str__(self):
    return self.name

  def __repr__(self):
    return "%s:%s" % (self.name, self.ips)

