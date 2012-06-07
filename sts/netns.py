'''
Utilites for launching and managing processes which run in and/or communicate
with network namespaces.

@author samw
'''

import itertools
import socket
from os import system

import deferred_io

ETH_P_ALL = 3 # The socket module doesn't have this. From C linux headers

class HostIOWorker(object):
  '''
  Wrapper class for DeferredIOWorker

  This class contains the functionality for spawning and communicating with a
  process in a network namespace. All of the simulator functionality is delegated
  to the wrapped DeferredIOWorker.
  '''

  # FIXME does this counter need to be threadsafe? itertools is not...
  _namespace_index = itertools.count(0) # for creating unique host device names

  def __init__(self, deferred_ioworker):
    self._deferred_ioworker = deferred_ioworker
    self._iface_index = HostIOWorker._namespace_index.next()
    self.init()

  def init(self):
    '''
    Set up and launch the network namespace.

    This method uses functionality that requires CAP_NET_ADMIN capabilites. This
    means that the calling method should check that the python process was
    launched as admin/superuser.

    Just called from __init__ for now. Separated for potential laziness.
    '''
    host_device = "heth%d" % (self._iface_index)
    guest_device = "geth%d" % (self._iface_index)
    # TODO fail with an exception on bad shell commands
    error_code = system("ip link add name %s type veth peer name %s" %
        (host_device, guest_device))

    error_code = system("ip link set %s promisc on" % (host_device,))
    error_code = system("ip link set %s up" % (host_device,))

    # make the host-side socket
    # do this before unshare/fork to make failure/cleanup easier
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, ETH_P_ALL)
    s.bind((host_device, ETH_P_ALL))

    # all else should have succeeded, so now we fork and unshare for the guest
    # TODO actually do this...

  ### Shutdown methods ###

  def _close_socket(self):
    '''
    Shutdown the socket that is set up.
    '''
    pass

  def close(self):
    self._close_socket()
    self._call_later(self._deferred_ioworker.close)

  def __del__(self): # TODO maybe this should be aliased to _close_socket instead?
    '''
    Clean up the socket at the very least
    '''
    self._close_socket()
