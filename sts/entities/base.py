# Copyright 2014 Ahmed El-Hassany
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Define base (mostly abstract) entities used by sts.
"""


import abc
import logging
from functools import partial

from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.util.procutils import popen_filtered
from sts.util.convenience import object_fullname
from sts.util.convenience import class_fullname
from sts.util.convenience import load_class
from sts.util.convenience import get_json_attr


def serialize_ofp_phy_port(port):
  """
  Serializes OpenFlow physical port to JSON Dict
  """
  attrs = ['port_no', 'hw_addr', 'name', 'config', 'state', 'curr',
           'advertised', 'supported', 'peer']
  json_dict = {'__type__': object_fullname(port)}
  print class_fullname(ofp_phy_port)
  for attr in attrs:
    value = getattr(port, attr, None)
    if hasattr(value, 'toStr'):
      value = value.toStr()
    json_dict[attr] = value
  return json_dict


def deserialize_ofp_phy_port(cls, json_dict):
  """
  De-Serializes JSON Dict to OpenFlow physical port
  """
  assert json_dict['__type__'] == class_fullname(cls)
  json_dict.pop('__type__')
  port = cls(**json_dict)
  return port

# Monkey patching
ofp_phy_port.to_json = lambda self: serialize_ofp_phy_port(self)
ofp_phy_port.from_json = classmethod(deserialize_ofp_phy_port)


class DirectedLinkAbstractClass(object):
  """
  A directed network link
  """
  __metaclass__ = abc.ABCMeta

  def __init__(self, start_node, start_port, end_node, end_port):
    """
    Init new directed link.

    start_port has to be member of start_node, likewise for end_port
    """
    if hasattr(start_node, 'has_port'):
      assert start_node.has_port(start_node)
    if hasattr(end_node, 'has_port'):
      assert end_node.has_port(end_node)
    self._start_node = start_node
    self._start_port = start_port
    self._end_node = end_node
    self._end_port = end_port

  @property
  def start_node(self):
    """The starting node"""
    return self._start_node

  @property
  def start_port(self):
    """The starting port"""
    return self._start_port

  @property
  def end_node(self):
    """The destination node"""
    return self._end_node

  @property
  def end_port(self):
    """The destination port"""
    return self._end_port

  def __eq__(self, other):
    return (self.start_node == getattr(other, 'start_node', None) and
            self.start_port == getattr(other, 'start_port', None) and
            self.end_node == getattr(other, 'end_node', None) and
            self.end_port == getattr(other, 'end_port', None))

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return "(%s:%s) -> (%s:%s)" % (self.start_node, self.start_port,
                                   self.end_node, self.end_port)

  def create_reversed_link(self):
    """Create a Link that is in the opposite direction of this Link."""
    return DirectedLinkAbstractClass(self.end_node, self.end_port,
                                     self.start_node, self.start_port)

  def to_json(self):
    """Serialize to JSON dict"""
    return {'__type__': object_fullname(self),
            'start_node': get_json_attr(self.start_node),
            'start_port': get_json_attr(self.start_port),
            'end_node': get_json_attr(self.end_node),
            'end_port': get_json_attr(self.end_port)}

  @classmethod
  def from_json(cls, json_dict):
    assert class_fullname(cls) == json_dict['__type__']
    start_node = json_dict['start_node']
    start_port = json_dict['start_port']
    end_node = json_dict['end_node']
    end_port = json_dict['end_port']
    if isinstance(start_node, dict) and start_node.get('__type__', None):
      start_node = load_class(start_node['__type__']).from_json(start_node)
    if isinstance(start_port, dict) and start_port.get('__type__', None):
      start_port = load_class(start_port['__type__']).from_json(start_port)
    if isinstance(end_node, dict) and end_node.get('__type__', None):
      end_node = load_class(end_node['__type__']).from_json(end_node)
    if isinstance(end_port, dict) and end_port.get('__type__', None):
      end_port = load_class(end_port['__type__']).from_json(end_port)
    return cls(start_node, start_port, end_node, end_port)


class BiDirectionalLinkAbstractClass(object):
  """
  An bi-directed network link
  """
  __metaclass__ = abc.ABCMeta

  def __init__(self, node1, port1, node2, port2):
    if hasattr(node1, 'has_port'):
      assert node1.has_port(port1)
    if hasattr(node2, 'has_port'):
      assert node2.has_port(port2)
    self._node1 = node1
    self._port1 = port1
    self._node2 = node2
    self._port2 = port2

  @property
  def node1(self):
    return self._node1

  @property
  def port1(self):
    return self._port1

  @property
  def node2(self):
    return self._node2

  @property
  def port2(self):
    return self._port2

  def __eq__(self, other):
    return ((self.node1 == getattr(other, 'node1', None) and
             self.port1 == getattr(other, 'port1', None) and
             self.node2 == getattr(other, 'node2', None) and
             self.port2 == getattr(other, 'port2', None)) or
             (self.node1 == getattr(other, 'node2', None) and
              self.port1 == getattr(other, 'port2', None) and
              self.node2 == getattr(other, 'node1', None) and
              self.port2 == getattr(other, 'port1', None)))

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return "(%s:%s) <-> (%s:%s)" % (self.node1, self.port1,
                                    self.node2, self.port2)

  def to_json(self):
    """Serialize to JSON dict"""
    return {'__type__': object_fullname(self),
            'node1': get_json_attr(self.node1),
            'port1': get_json_attr(self.port1),
            'node2': get_json_attr(self.node2),
            'port2': get_json_attr(self.port2)}

  @classmethod
  def from_json(cls, json_dict):
    assert class_fullname(cls) == json_dict['__type__']
    node1 = json_dict['node1']
    port1 = json_dict['port1']
    node2 = json_dict['node2']
    port2 = json_dict['port2']
    if isinstance(node1, dict) and node1.get('__type__', None):
      node1 = load_class(node1['__type__']).from_json(node1)
    if isinstance(port1, dict) and port1.get('__type__', None):
      port1 = load_class(port1['__type__']).from_json(port1)
    if isinstance(node2, dict) and node2.get('__type__', None):
      node2 = load_class(node2['__type__']).from_json(node2)
    if isinstance(port2, dict) and port2.get('__type__', None):
      port2 = load_class(port2['__type__']).from_json(port2)
    return cls(node1, port1, node2, port2)


class SSHEntity(object):
  """
  Controls an entity via ssh.
  """

  def __init__(self, host, port=22, username=None, password=None,
               key_filename=None, cwd=None, label=None, redirect_output=False,
               block=False):
    """
    If username, password, and key_filename are None, the SSH will be use the
    default ssh key loaded into the system and will work if the destination
    host is configured to accept that key.

    Args:
      host: the server address to connect to.
      port: the server port to connect to (default 22)
      username: the username to authenticate as (default local username)
      password: password to authenticate or to unlock the private key
      key_filename: private key for authentication
      cwd: working dir for commands
      label: human readable label to associated with output
      redirect_output: If true remote stdout & stderr are redirected to stdout
      block: if True execute_command will block until the command is complete
    """
    self._host = host
    self._port = port
    self._username = username
    self._password = password
    self._key_filename = key_filename
    self._ssh_client = None
    self._ssh_cls = None
    self.redirect_output = redirect_output
    self.block = block
    self.cwd = cwd
    self.label = label or ""

    if self._ssh_cls is None:
      try:
        import paramiko
      except ImportError:
        raise RuntimeError('''Must install paramiko to use ssh: \n'''
                           ''' $ sudo pip install paramiko ''')
      # Suppress normal SSH messages
      logging.getLogger("paramiko").setLevel(logging.WARN)
      self._ssh_cls = paramiko.SSHClient
    self.log = logging.getLogger("SSHEntity")

  @property
  def host(self):
    """The server address to connect to"""
    return self._host

  @property
  def port(self):
    """The server port to connect to"""
    return self._port

  @property
  def username(self):
    """The username to authenticate as (default local username)"""
    return self._username

  @property
  def password(self):
    """Password to authenticate or to unlock the private key."""
    return self._password

  @property
  def key_filename(self):
    """Private key for authentication"""
    return self._key_filename

  @property
  def ssh_cls(self):
    """
    Returns reference to the SSH Client class
    """
    return self._ssh_cls

  @property
  def check_key_policy(self):
    """
    Returns the the policy for missing host keys

    Default: accept all keys
    """
    try:
      import paramiko
    except ImportError:
      raise RuntimeError('''Must install paramiko to use ssh: \n'''
                         ''' $ sudo pip install paramiko ''')
    return paramiko.AutoAddPolicy()

  @property
  def ssh_client(self):
    """Returns instance of the ssh client

    Will connect to the host if not already connected.
    """
    if self._ssh_client is None:
      self._ssh_client = self.ssh_cls()
      # Ignore host identify check
      self._ssh_client.set_missing_host_key_policy(self.check_key_policy)
      self._ssh_client.connect(hostname=self.host, port=self.port,
                               username=self.username, password=self.password,
                               key_filename=self.key_filename)
    return self._ssh_client

  def get_new_session(self):
    """Return new ssh session handler to the host"""
    ssh = self.ssh_client
    transport = ssh.get_transport()
    session = transport.open_channel(kind='session')
    return session

  def execute_command(self, cmd):
    """
    Execute command remotely and return the stdout results
    """
    #  procutils was meant to be a leaf dependency
    from sts.util.procutils import _prefix_thread
    from sts.util.procutils import color_normal
    from sts.util.procutils import color_error

    if self.cwd is not None:
      cmd = "cd " + self.cwd + " ;" + cmd

    r_stdin, r_stdout, r_stderr = self.ssh_client.exec_command(cmd)

    if self.redirect_output:
      stdout_thread = _prefix_thread(r_stdout,
                                     partial(color_normal, label=self.label))
      stderr_thread = _prefix_thread(r_stderr,
                                     partial(color_error, label=self.label))
      if self.block:
        channel = r_stdout.channel
        while True:
          if channel.recv_ready() is False and channel.exit_status_ready():
            break
      return ""
    else:
      # dealing directly with the channel makes it easier to detect exit status
      reply = ""
      channel = r_stdout.channel
      while True:
        if channel.recv_ready():
          reply += channel.recv(100)  # arbitrary
        elif channel.recv_ready() is False and channel.exit_status_ready():
          break
      channel.close()
      return reply

  def __del__(self):
    if self._ssh_client:
      try:
        self._ssh_client.close()
      except Exception as exp:
        self.log.warn("Error at closing ssh connection: '%s'" % exp)


class LocalEntity(object):
  """
  Controls an entity via local unix command.
  """

  def __init__(self, cwd=None, label=None, redirect_output=False):
    """
    Args:
      cwd: working dir for commands
      label: human readable label to associated with output
      redirect_output: If true remote stdout & stderr are redirected to stdout
    """
    self.cwd = cwd
    self.label = label or ""
    self.redirect_output = redirect_output
    self.log = logging.getLogger("LocalEntity")

  def execute_command(self, cmd):
    """
    Execute command locally and return the stdout results
    """
    process = popen_filtered("[%s]" % self.label, cmd, self.cwd,
                             shell=True, redirect_output=self.redirect_output)
    output = ""
    while True:
      recv = process.stdout.read(100)  # arbitrary
      output += recv
      if recv == '' and process.poll() is not None:
        break
    if self.redirect_output:
      return ''
    return output
