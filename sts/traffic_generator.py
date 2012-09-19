
from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from sts.dataplane_traces.trace import DataplaneEvent

class TrafficGenerator (object):
  """
  Generate sensible randomly generated (openflow) events
  """

  def __init__(self, random=random.Random()):
    self.random = random

    self._packet_generators = {
      "icmp_ping" : self.icmp_ping
    }

  def generate(self, packet_type, host):
    if packet_type not in self._packet_generators:
      raise AttributeError("Unknown event type %s" % str(packet_type))

    # Inject the packet through one of the hosts' interfaces
    if len(host.interfaces) < 1:
      raise RuntimeError("No interfaces to choose from on host %s!" %
                         (str(host)))

    interface = self.random.choice(host.interfaces)
    packet = self._packet_generators[packet_type](interface)
    host.send(interface, packet)
    return DataplaneEvent(interface, packet)

  # Generates an ICMP ping, and injects it through the interface
  def icmp_ping(self, interface):
    # randomly choose an in_port.
    e = ethernet()
    e.src = interface.hw_addr
    # TODO(cs): need a better way to create random MAC addresses
    # TODO(cs): allow the user to specify a non-random dst address
    e.dst = EthAddr(struct.pack("Q",self.random.randint(1,0xFF))[:6])
    e.type = ethernet.IP_TYPE
    ipp = ipv4()
    ipp.protocol = ipv4.ICMP_PROTOCOL
    if hasattr(interface, 'ips'):
      ipp.srcip = self.random.choice(interface.ips)
    else:
      ipp.srcip = IPAddr(self.random.randint(0,0xFFFFFFFF))
    ipp.dstip = IPAddr(self.random.randint(0,0xFFFFFFFF))
    ping = icmp()
    ping.type = TYPE_ECHO_REQUEST
    ping.payload = "PingPing" * 6
    ipp.payload = ping
    e.payload = ipp
    return e

