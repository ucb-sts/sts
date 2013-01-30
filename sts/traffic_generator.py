
from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from sts.dataplane_traces.trace import DataplaneEvent
import random

class TrafficGenerator (object):
  """
  Generate sensible randomly generated (openflow) events
  """

  def __init__(self, random=random.Random()):
    self.random = random
    self.hosts = []

    self._packet_generators = {
      "icmp_ping" : self.icmp_ping
    }

  def set_hosts(self, hosts):
    ''' Let us know how to set the destination addresses '''
    self.hosts = set(hosts)

  def generate(self, packet_type, host, self_pkt=False):
    if packet_type not in self._packet_generators:
      raise AttributeError("Unknown event type %s" % str(packet_type))

    # Inject the packet through one of the hosts' interfaces
    if len(host.interfaces) < 1:
      raise RuntimeError("No interfaces to choose from on host %s!" %
                         (str(host)))

    interface = self.random.choice(host.interfaces)
    destination_interface = None
    if self_pkt:
      # Send a packet to ourself to help the controller learn our location
      destination_interface = interface
    elif self.hosts:
      destination = self.random.choice(list(self.hosts - set([host])))
      destination_interface = self.random.choice(destination.interfaces)

    packet = self._packet_generators[packet_type](interface, destination_interface)
    host.send(interface, packet)
    return DataplaneEvent(interface, packet)

  # Generates an ICMP ping, and injects it through the interface
  def icmp_ping(self, interface, destination_interface):
    # randomly choose an in_port.
    e = ethernet()
    e.src = interface.hw_addr
    if destination_interface is not None:
      e.dst = destination_interface.hw_addr
    else:
      # TODO(cs): need a better way to create random MAC addresses
      e.dst = EthAddr(struct.pack("Q",self.random.randint(1,0xFF))[:6])
    e.type = ethernet.IP_TYPE
    ipp = ipv4()
    ipp.protocol = ipv4.ICMP_PROTOCOL
    if hasattr(interface, 'ips'):
      ipp.srcip = self.random.choice(interface.ips)
    else:
      ipp.srcip = IPAddr(self.random.randint(0,0xFFFFFFFF))
    if destination_interface is not None and hasattr(destination_interface, 'ips'):
      ipp.dstip = self.random.choice(destination_interface.ips)
    else:
      ipp.dstip = IPAddr(self.random.randint(0,0xFFFFFFFF))
    ping = icmp()
    ping.type = self.random.choice([TYPE_ECHO_REQUEST,TYPE_ECHO_REPLY])
    ping.payload = "PingPing" * 6
    ipp.payload = ping
    e.payload = ipp
    return e

