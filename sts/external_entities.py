'''
A factory module to create sockets or other interfaces to edge entities.

@author samw
'''

import itertools
import socket
import subprocess
import fcntl
import struct
from os import geteuid
from exceptions import EnvironmentError
from platform import system
from pox.lib.addresses import EthAddr

ETH_P_ALL = 3 # The socket module doesn't have this. From C linux headers

# FIXME does this counter need to be threadsafe? itertools is not...
_netns_index = itertools.count(0) # for creating unique host device names

def get_eth_address_for_interface(ifname):
  '''Returns an EthAddr object from the interface specified by the argument.

  interface is a string, commonly eth0, wlan0, lo.'''
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
  return EthAddr(''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1])

def netns(cmd="xterm"):
  '''
  Set up and launch cmd in a new network namespace.

  Returns a tuple of the (socket, Popen object of unshared project in netns, EthAddr of guest device).

  This method uses functionality that requires CAP_NET_ADMIN capabilites. This
  means that the calling method should check that the python process was
  launched as admin/superuser.
  '''

  if system() != 'Linux':
    raise EnvironmentError('network namespace functionality requires a Linux environment')

  uid = geteuid()
  if uid != 0:
    # user must have CAP_NET_ADMIN, which doesn't have to be su, but most often is
    raise EnvironmentError("superuser privileges required to launch network namespace")

  iface_index = _netns_index.next()

  host_device = "heth%d" % (iface_index)
  guest_device = "geth%d" % (iface_index)

  try:
    null = file("/dev/null", 'w')
    for dev in (host_device, guest_device):
      if subprocess.call(['ip', 'link', 'show', dev], stdout=null, stderr=null) == 0:
        subprocess.check_call(['ip', 'link', 'del', dev])

    subprocess.check_call(['ip','link','add','name',host_device,'type','veth','peer','name',guest_device])
    subprocess.check_call(['ip','link','set',host_device,'promisc','on'])
    subprocess.check_call(['ip','link','set',host_device,'up'])
  except subprocess.CalledProcessError:
    raise # TODO raise a more informative exception

  guest_eth_addr = get_eth_address_for_interface(guest_device)

  # make the host-side socket
  # do this before unshare/fork to make failure/cleanup easier
  s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, ETH_P_ALL)
  s.bind((host_device, ETH_P_ALL))
  s.setblocking(0) # set non-blocking

  # all else should have succeeded, so now we fork and unshare for the guest
  guest = subprocess.Popen(["unshare", "-n", cmd])

  # push down the guest device into the netns
  try:
    subprocess.check_call(['ip', 'link', 'set', guest_device, 'netns', str(guest.pid)])
  except subprocess.CalledProcessError:
    s.close()
    raise # TODO raise a more informative exception

  return (s, guest, guest_eth_addr, guest_device)
