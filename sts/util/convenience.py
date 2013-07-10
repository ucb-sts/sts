# Copyright 2011-2013 Colin Scott
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

from pox.lib.addresses import EthAddr, IPAddr
import time
import re
import os
import errno
import socket
import random
import types
import struct

# don't use the standard instance - we don't want to be seeded
true_random = random.Random()

def is_sorted(l):
  return all(l[i] <= l[i+1] for i in xrange(len(l)-1))

def is_strictly_sorted(l):
  return all(l[i] < l[i+1] for i in xrange(len(l)-1))

def timestamp_string():
  return time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())

def find(f, seq):
  """Return first item in sequence where f(item) == True."""
  for item in seq:
    if f(item):
      return item

def find_index(f, seq):
  """Return the index of the first item in sequence where f(item) == True."""
  for index, item in enumerate(seq):
    if f(item):
      return index

def mkdir_p(dst):
  try:
    os.makedirs(dst)
  except OSError as exc:
    if exc.errno == errno.EEXIST and os.path.isdir(dst):
      pass
    else:
      raise

def random_eth_addr():
  return EthAddr(struct.pack("Q", true_random.randint(1,0xFF))[:6])

def random_ip_addr():
  return IPAddr(true_random.randint(0,0xFFFFFFFF))

def address_is_ip(address):
  return re.match("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", address)

def port_used(address='127.0.0.1', port=6633):
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  try:
    s.bind((address, port))
    s.listen(1)
    s.close()
    return False
  except Exception, e:
    # TODO(cs): catch specific errors
    return True

def find_port(port_spec):
  if isinstance(port_spec, xrange):
    port_spec = list(port_spec)
  port_gen = None
  if isinstance(port_spec, int):
    def port_gen():
      yield port_spec
      raise Exception("Fixed port %d is busy. Consider specifying a range or a lambda " % port_spec)
  elif isinstance(port_spec, list):
    def port_gen():
      cands = list(port_spec)
      true_random.shuffle(cands)
      for c in cands:
        yield c
      raise Exception("Port list/range %s exhausted" % str(port_spec))
  elif isinstance(port_spec, types.FunctionType) or isinstance(port_spec, types.LambdaType):
    port_gen = port_spec

  gen = port_gen()
  for attempt in range(0,100):
    candidate = gen.next()
    if not port_used(port=candidate):
      return candidate
  raise Exception("Could not find a port in 100 tries")

# TODO(cs): this function don't appear to be invoked?
def find_ports(**kwargs):
  return { k : find_port(v) for k, v in kwargs.iteritems() }

class ExitCode(object):
  def __init__(self, exit_code):
    self.exit_code = exit_code
