# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
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

import unittest
import sys
import os
import time
from threading import Thread
import logging
log = logging.getLogger()
from sts.util.socket_mux.server_socket_multiplexer import *
from sts.util.socket_mux.sts_socket_multiplexer import *

sys.path.append(os.path.dirname(__file__) + "/../../..")

class MultiplexerTest(unittest.TestCase):
  client_messages = [ "foo", "bar", "baz" ]

  def setup_server(self, address):
    import socket
    mux_select = ServerMultiplexedSelect()
    ServerMockSocket.bind_called = False
    listener = ServerMockSocket(socket.AF_UNIX, socket.SOCK_STREAM,
                     set_true_listen_socket=mux_select.set_true_listen_socket)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen(16)
    return (mux_select, listener)

  def setup_client(self, num_socks, address):
    from pox.lib.util import connect_socket_with_backoff
    io_master = MultiplexedSelect()
    socket = connect_socket_with_backoff(address=address)
    io_worker = io_master.create_worker_for_socket(socket)
    io_master.set_true_io_worker(io_worker)
    # TODO(cs): unused variable demux
    demux = STSSocketDemultiplexer(io_worker, address)
    mock_socks = []
    for i in xrange(num_socks):
      mock_socket = STSMockSocket(None, None)
      mock_socket.connect(address)
      mock_socket.send(self.client_messages[i])
      mock_socks.append(mock_socket)
    io_master.select(mock_socks, mock_socks, [])

  def wait_for_next_accept(self, listener, mux_select):
    log.info("waiting for next accept")
    rl = []
    while listener not in rl:
      (rl, _, _) = mux_select.select([listener], [], [], 0.1)

  def test_basic(self):
    address = "basic_pipe"
    try:
      t = Thread(target=self.setup_client, args=(1,address,), name="MainThread")
      t.start()
      (mux_select, listener) = self.setup_server(address)
      self.wait_for_next_accept(listener, mux_select)
      mock_sock = listener.accept()[0]
      (rl, _, _) = mux_select.select([mock_sock], [], [])
      start = last = time.time()
      while mock_sock not in rl:
        time.sleep(0.05)
        if time.time() - start > 5:
          self.fail("Did not find socket in rl in 5 seconds")
        elif time.time() - last > 1:
          log.debug("waiting for socket %s in rl %s..." % ( str(mock_sock), repr(rl)))
          last = time.time()
        (rl, _, _) = mux_select.select(rl, [], [])
      d = mock_sock.recv(2048)
      self.assertEqual(self.client_messages[0], d)
    finally:
      try:
        os.unlink(address)
      except OSError:
        if os.path.exists(address):
          raise RuntimeError("can't remove PIPE socket %s" % str(address))

  def test_three_incoming(self):
    address = "three_pipe"
    try:
      t = Thread(target=self.setup_client, args=(3,address,), name="MainThread")
      t.start()
      (mux_select, listener) = self.setup_server(address)
      for i in xrange(len(self.client_messages)):
        self.wait_for_next_accept(listener, mux_select)
        mock_sock = listener.accept()[0]
        (rl, _, _) = mux_select.select([mock_sock], [], [])
        start = last = time.time()
        while mock_sock not in rl:
          if time.time() - start > 5:
            self.fail("Did not find socket in rl in 5 seconds")
          elif time.time() - last > 1:
            log.debug("waiting for socket %s in rl %s..." % ( str(mock_sock), repr(rl)))
            last = time.time()
          (rl, _, _) = mux_select.select(rl, [], [])
          time.sleep(0.05)
        d = mock_sock.recv(2048)
        # order should be deterministic
        self.assertEqual(self.client_messages[i], d)
    finally:
      try:
        os.unlink(address)
      except OSError:
        if os.path.exists(address):
          raise RuntimeError("can't remove PIPE socket %s" % str(address))

