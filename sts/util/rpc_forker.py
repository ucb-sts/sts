
from abc import *
import os
from SimpleXMLRPCServer import SimpleXMLRPCServer
import xmlrpclib
import sys
import marshal
import signal
from sts.util.convenience import find_port
from pox.lib.util import connect_with_backoff
import logging
log = logging.getLogger("rpc_forker")

def test_serialize_response(*args):
  for arg in args:
    try:
      xmlrpclib.dumps((arg,), methodresponse=True)
    except Exception as e:
      print "Could not serialize arg %s" % str(arg)
      raise e

def test_serialize_request(methodname, *args):
  for arg in args:
    try:
      xmlrpclib.dumps((arg,), methodresponse=True, methodname=methodname)
    except Exception as e:
      print "Could not serialize arg %s" % str(arg)
      raise e

class TaskRegistry(object):
  ''' Maintains code for tasks to be Forked. '''
  def __init__(self):
    self._name_to_task = {}

  def register_task(self, task_name, code_block):
    self._name_to_task[task_name] = code_block

  def get_task(self, task_name):
    if task_name not in self._name_to_task:
      raise ValueError("Task %s is not registered" % task_name)
    return self._name_to_task[task_name]

class Forker(object):
  ''' Easily fork a job and retrieve the results '''
  # Implementation:
  #  - parent forks a child
  #  - child runs an RPC server
  #  - parent invokes (blocking) RPC on child
  #  - child eventually returns, and shuts itself down
  #  - parent returns result to caller.
  __metaclass__ = ABCMeta

  def __init__(self):
    self._task_registry = TaskRegistry()

  @abstractmethod
  def register_task(self, task_name, code_block):
    ''' Register a new task to be invoked by this Forker. Parameters:
      - task_name: the name of the task to be run, later passed to fork()
      - code_block: a function object to be invoked via RPC
        in the child process. *Must not* depend on any environment state
        contained in its closure.
    '''
    pass

  @abstractmethod
  def fork(self, task_name, *args, **kws):
    ''' Fork off a child process and invoke the child RPC method. Return the json_hash
    sent by the child.

    Raises a ValueError if task_name is not registered.'''
    pass

  def _new_child_url(self, ip='localhost', port=None):
    # Called within the parent process
    if port is None:
      port = find_port(xrange(3000,6000))
    return (ip, port)

  def _invoke_child_rpc(self, ip, port, task_name, *args):
    # Called within the parent process
    child_url = "http://" + str(ip) + ":" + str(port) + "/"
    log.debug("Invoking task %s on child %s" % (task_name, child_url,))
    test_serialize_request(task_name, *args)
    proxy = xmlrpclib.ServerProxy(child_url, allow_none=True)
    def invoke_child():
      return getattr(proxy, task_name)(*args)
    child_return = connect_with_backoff(invoke_child)
    # Magic to close the underlying socket. I'm not sure if this is actually
    # needed? See ServerProxy.__call__ in:
    # http://hg.python.org/cpython/file/2.7/Lib/xmlrpclib.py
    proxy("close")()
    return child_return

  def _initialize_child_rpc_server(self, ip, port):
    # Called within the child process.
    # The child's RPC methods must registered through register_task()
    self.server = SimpleXMLRPCServer((ip, port), allow_none=True,
                                     bind_and_activate=False)
    self.server.allow_reuse_address = True
    self.server.server_bind()
    self.server.server_activate()

class LocalForker(Forker):
  # set of process ids that are currently running. These are all killed upon
  # signal reception.
  _active_pids = set()

  @staticmethod
  def kill_all():
    for pid in list(LocalForker._active_pids):
      os.kill(pid, signal.SIGTERM)
    LocalForker._active_pids.clear()

  def register_task(self, task_name, code_block):
    self._task_registry.register_task(task_name, code_block)

  def fork(self, task_name, *args, **kws):
    # N.B. get_task raises an exception if task_name is not registered
    task = self._task_registry.get_task(task_name)
    (ip, port) = self._new_child_url()
    # TODO(cs): use subprocess to spawn baby snakes instead of os.fork()
    pid = os.fork()
    if pid == 0: # Child
      # Send parents interrupts to the child
      os.setsid()
      self._initialize_child_rpc_server(ip, port)
      self.server.register_function(task, task_name)
      self.server.handle_request()
      sys.exit(0)
    else: # Parent
      LocalForker._active_pids.add(pid)
      try:
        child_return = self._invoke_child_rpc(ip, port,
                                              task_name, *args, **kws)
        LocalForker._active_pids.remove(pid)
      except xmlrpclib.Fault as err:
        print "An RPC fault occurred"
        print "Fault code: %d" % err.faultCode
        print "Fault string: %s" % err.faultString
        raise

      os.waitpid(pid, 0)
      return child_return

class RemoteForker(Forker):
  def __init__(self, server_info_list):
    ''' cycles through server_info_list for each invocation of fork() '''
    pass

  def register_task(self, task_name, code_block):
    # Serialize the code_block so we can send it across the wire to the child
    serialized_code = marshal.dumps(code_block.func_code)\
                             .encode('base64')
    self._task_registry.register_task(task_name, serialized_code)

  def fork(self, task_name, *args, **kws):
    # TODO(cs): Need to define a main() method for the child process, tell child what URL
    # to bind to via command line arguments, and have child boot
    # up an RPC server. Then send over the TaskRegistry's task code over the wire,
    # have the child deserialize the base64 encoded func object, and have the
    # child register the tasks as RPC stubs.
    task = self._task_registry.get_task(task_name)
    pass
