
from abc import *
import os
from SimpleXMLRPCServer import SimpleXMLRPCServer
import xmlrpclib
import sys

class Forker(object):
  ''' Easily fork a job and retrieve the results '''
  __metaclass__ = ABCMeta

  def __init__(self, ip='localhost', port=3370):
    self.ip = ip
    self.port = port
    self.server = SimpleXMLRPCServer((ip, port), allow_none=True)
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
    print "client_return!:" % client_return
    self.client_return = client_return
    return None

class LocalForker(Forker):
  def fork(self, code_block):
    # TODO(cs): use subprocess instead to spawn baby snakes
    pid = os.fork()
    if pid == 0: # Child
      self._invoke_child(code_block)
    else: # Parent
      self.server.handle_request()
    return self.client_return

class RemoteForker(Forker):
  def __init__(self, server_info_list):
    ''' cycles through server_info_list for each invocation of fork() '''
    pass

  def fork(self, code_block):
    # Would need bidirectional communication between parent and child..
    # (Need to send code_block to client)
    pass

