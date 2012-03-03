
from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *

class TrafficGenerator (object):
  """
  Generate sensible randomly generated (openflow) events
  """

  def __init__(self, random):
    self.random = random

    self._packet_generators = {
      "icmp_ping" : self.icmp_ping
    }

  def generate(self, packet_type, switch_impl):
    if packet_type not in self._packet_generators:
      raise AttributeError("Unknown event type %s" % str(packet_type))

    return self._packet_generators[packet_type](switch_impl)

  # Generates an ICMP ping, and feeds it to the switch_impl_impl
  def icmp_ping(self, switch_impl):
    # randomly choose an in_port.
    if len(switch_impl.ports) == 0:
      raise RuntimeError("No Ports Registered on switch_impl! %s" % str(switch_impl)) # TODO:
    # TODO: just use access links for packet ins -- not packets from within the network
    in_port = self.random.choice(switch_impl.ports.values())
    e = ethernet()
    # TODO: need a better way to create random MAC addresses
    e.src = EthAddr(struct.pack("Q",self.random.randint(1,0xFF))[:6])
    e.dst = in_port.hw_addr
    e.type = ethernet.IP_TYPE
    ipp = ipv4()
    ipp.protocol = ipv4.ICMP_PROTOCOL
    ipp.srcip = IPAddr(self.random.randint(0,0xFFFFFFFF))
    ipp.dstip = IPAddr(self.random.randint(0,0xFFFFFFFF))
    ping = icmp()
    ping.type = TYPE_ECHO_REQUEST
    ping.payload = "PingPing" * 6
    ipp.payload = ping
    e.payload = ipp

    buffer_id = self.random.randint(0,0xFFFFFFFF)
    reason = None

    # Feed the packet to the switch_impl
    switch_impl.process_packet(e, in_port=in_port.port_no)
