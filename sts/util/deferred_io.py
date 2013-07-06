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

'''
Created on Feb 25, 2012

@author: aw, cs
'''
import logging
import Queue

log = logging.getLogger()

class DeferredIOWorker(object):
  '''
  Wrapper class for RecocoIOWorkers.

  Rather than actually sending/receiving right away, queue the data.
  Then there are separate methods for actually sending the data via
  the wrapped io_worker

  io_worker: io_worker to wrap
  '''
  def __init__(self, io_worker):
    self._io_worker = io_worker
    self._io_worker.set_receive_handler(self.io_worker_receive_handler)
    # Thread-safe read and write queues of indefinite length
    # TODO(cs): no need for thread safety anymore
    self._receive_queue = Queue.Queue()
    self._send_queue = Queue.Queue()
    # Read buffer that we present to clients
    self._receive_buf = ""
    # Whether this control channel is currently blocked. If False, passes
    # through packets.
    self._currently_blocked = False

  def block(self):
    ''' Stop allowing data through until unblock() is called '''
    self._currently_blocked = True

  def unblock(self):
    ''' Allow data through, and flush buffers '''
    self._currently_blocked = False
    while not self._send_queue.empty():
      data = self._send_queue.get()
      self._actual_send(data)
    while not self._receive_queue.empty():
      data = self._receive_queue.get()
      self._actual_receive(data)

  def send(self, data):
    ''' send data from the client side. fire and forget. '''
    if self._currently_blocked:
      self._send_queue.put(data)
    else:
      self._actual_send(data)

  def _actual_send(self, data):
    self._io_worker.send(data)

  def _actual_receive(self, data):
    self._receive_buf += data
    self._client_receive_handler(self)

  def set_receive_handler(self, block):
    ''' Called by client '''
    self._client_receive_handler = block

  def peek_receive_buf(self):
    ''' Called by client '''
    return self._receive_buf

  def consume_receive_buf(self, l):
    ''' called by client to consume receive buffer '''
    assert(len(self._receive_buf) >= l)
    self._receive_buf = self._receive_buf[l:]

  def io_worker_receive_handler(self, io_worker):
    ''' called from io_worker (recoco thread, after the Select loop pushes onto io_worker) '''
    # Consume everything immediately
    data = io_worker.peek_receive_buf()
    io_worker.consume_receive_buf(len(data))
    if self._currently_blocked:
      # thread-safe queue
      self._receive_queue.put(data)
    else:
      self._actual_receive(data)

  @property
  def currently_blocked(self):
    ''' Return whether we are currently allowing data through '''
    return self._currently_blocked

  # ------- Delegation functions. ---------
  # TODO(cs): is there a more pythonic way to implement delegation?

  def fileno(self):
    # thread safety shoudn't matter here
    return self._io_worker.fileno()

  def close(self):
    self._io_worker.close()

  @property
  def closed(self):
    return self._io_worker.closed

  @property
  def socket(self):
    return self._io_worker.socket
