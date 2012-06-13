'''
Utilites for launching and managing processes which run in and/or communicate
with network namespaces.

@author samw
'''

import itertools
import socket
import subprocess

ETH_P_ALL = 3 # The socket module doesn't have this. From C linux headers

# FIXME does this counter need to be threadsafe? itertools is not...
_netns_index = itertools.count(0) # for creating unique host device names

def netns():
  '''
  Set up and launch the network namespace.

  This method uses functionality that requires CAP_NET_ADMIN capabilites. This
  means that the calling method should check that the python process was
  launched as admin/superuser.

  Returns an IOWorker that wraps the raw socket.
  '''
  global _netns_index

  iface_index = _netns_index.next()

  host_device = "heth%d" % (iface_index)
  guest_device = "geth%d" % (iface_index)

  try:
    subprocess.check_call(['ip','link','add','name',host_device,'type','veth','peer','name',guest_device])
    subprocess.check_call(['ip','link','set',host_device,'promisc','on'])
    subprocess.check_call(['ip','link','set',host_device,'up'])
  except subprocess.CalledProcessError:
    raise # TODO raise a more informative exception

  # make the host-side socket
  # do this before unshare/fork to make failure/cleanup easier
  s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, ETH_P_ALL)
  s.bind((host_device, ETH_P_ALL))

  # all else should have succeeded, so now we fork and unshare for the guest
  guest = Popen(["unshare", "-n", "xterm"])
  #TODO get this to somehow open up in a screen/tmux session?

  # push down the guest device into the netns
  try:
    subprocess.check_call(['ip', 'link', 'set', guest_device, 'netns', guest.pid])
  except subprocess.CalledProcessError:
    raise # TODO raise a more informative exception
  finally:
    s.close()

  # wrap the socket with an IOWorker
