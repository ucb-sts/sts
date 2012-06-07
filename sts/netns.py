'''
Utilites for launching and managing processes which run in and/or communicate
with network namespaces.

@author samw
'''

import itertools
import socket
import subprocess

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
    self.init(HostIOWorker._namespace_index.next())

  def init(self, iface_index):
    '''
    Set up and launch the network namespace.

    This method uses functionality that requires CAP_NET_ADMIN capabilites. This
    means that the calling method should check that the python process was
    launched as admin/superuser.

    Just called from __init__ for now. Separated for potential laziness.
    '''
    host_device = "heth%d" % (iface_index)
    guest_device = "geth%d" % (iface_index)

    try:
      subprocess.check_call(['ip','link','add','name',host_device,'type','veth','peer','name',guest_device])
      subprocess.check_call(['ip','link','set',host_device,'promisc','on'])
      subprocess.check_call(['ip','link','set',host_device,'up'])
    except subprocess.CalledProcessError:
      pass # TODO raise a more informative exception

    # make the host-side socket
    # do this before unshare/fork to make failure/cleanup easier
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, ETH_P_ALL)
    s.bind((host_device, ETH_P_ALL))
    self._socket = s

    # all else should have succeeded, so now we fork and unshare for the guest
    guest = Popen(["unshare", "-n", "/bin/bash"])
    #TODO get this to somehow open up in a screen/tmux session?

    # push down the guest device into the netns
    try:
      subprocess.check_call(['ip', 'link', 'set', guest_device, 'netns', guest.pid])
    except subprocess.CalledProcessError:
      pass # TODO raise a more informative exception
    finally:
      s.close()

    self._guest = guest

  ### Shutdown methods ###

  def _close_socket(self):
    '''
    Shutdown the socket that is set up.
    '''
    self._socket.close()
    # TODO force self.guest to terminate with SIG_something

  def close(self):
    self._close_socket()
    self._call_later(self._deferred_ioworker.close)

  __del__ = _close_socket # close socket at the very least!
