
from abc import *
import os
from SimpleXMLRPCServer import SimpleXMLRPCServer
import xmlrpclib
import sys
from sts.util.convenience import find_port

class Forker(object):
  ''' Easily fork a job and retrieve the results '''
  __metaclass__ = ABCMeta

  def __init__(self, ip='localhost', port=None):
    self.ip = ip
    if port is None:
      port = find_port(xrange(3000,6000))
    self.port = port
    self.server = SimpleXMLRPCServer((ip, port), allow_none=True,
                                     bind_and_activate=False)
    self.server.allow_reuse_address = True
    self.server.server_bind()
    self.server.server_activate()
    self.server.register_function(self.return_to_parent, "return_to_parent")
    self.client_return = None

  @abstractmethod
  def fork(self, code_block):
    ''' Fork off a child process, and run code_block. Return the json_hash
    sent by the client'''
    pass

  def _invoke_child(self, code_block):
    parent_url = "http://" + str(self.ip) + ":" + str(self.port) + "/"
    proxy = xmlrpclib.ServerProxy(parent_url, allow_none=True)
    client_return = code_block()
    proxy.return_to_parent(client_return)
    sys.exit(0)

  def return_to_parent(self, client_return):
    ''' Invoked by child process to return a value '''
    self.client_return = client_return
    return None

  def close(self):
    self.server.socket.close()

class LocalForker(Forker):
  def fork(self, code_block):
    # TODO(cs): use subprocess instead to spawn baby snakes
    pid = os.fork()
    if pid == 0: # Child
      self._invoke_child(code_block)
    else: # Parent
      self.server.handle_request()
      os.waitpid(pid, 0)
    return self.client_return

class RemoteForker(Forker):
  def __init__(self, server_info_list):
    ''' cycles through server_info_list for each invocation of fork() '''
    pass

  def fork(self, code_block):
    # Would need bidirectional communication between parent and child..
    # (Need to send code_block to client)
    pass

