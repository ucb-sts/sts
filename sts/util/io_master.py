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

import errno
import sys
import logging
import select
import socket
import time
import threading

from pox.lib.util import makePinger
from pox.lib.ioworker.io_worker import IOWorker

log = logging.getLogger("io_master")

class STSIOWorker(IOWorker):
  """ An IOWorker that works with our IOMaster """
  def __init__(self, socket, on_close):
    IOWorker.__init__(self)
    self.socket = socket
    self.closed = False
    # (on_close factory method hides details of the Select loop)
    self.on_close = on_close

  def fileno(self):
    """ Return the wrapped sockets' fileno """
    return self.socket.fileno()

  def send(self, data):
    """ send data from the client side. fire and forget. """
    return IOWorker.send(self, data)

  def close(self):
    """ Register this socket to be closed. fire and forget """
    # (don't close until Select loop is ready)
    IOWorker.close(self)
    # on_close is a function not a method
    self.on_close(self)

# Note that IOMaster is used as the main select loop in POX (debugger branch)
class IOMaster(object):
  """
  an IO handler that handles the select work for our IO worker
  """
  _select_timeout = 5
  _BUF_SIZE = 8192

  def __init__ (self):
    self._workers = set()
    self.pinger = makePinger()
    self.closed = False
    self._close_requested = False
    self._in_select = 0

  def create_worker_for_socket(self, socket):
    '''
    Return an IOWorker wrapping the given socket.
    '''
    # Called from external threads.
    # Does not register the IOWorker immediately with the select loop --
    # rather, adds a command to the pending queue

    # Our callback for io_worker.close():
    def on_close(worker):
      worker.socket.close()
      worker.closed = True
      self._workers.discard(worker)

    worker = STSIOWorker(socket, on_close=on_close)
    self._workers.add(worker)
    return worker

  def monkey_time_sleep(self):
    """monkey patches time.sleep to use this io_masters's time.sleep"""
    self.original_time_sleep = time.sleep
    # keep time._orig_sleep around for interrupt handler (procutils)
    time._orig_sleep = time.sleep
    time.sleep = self.sleep

  def raw_input(self, prompt):
    """ raw_input replacement that enables background IO to take place.
        NOTE: this migrates the IO to a specifically created BackgroundIOThread
        while readline's raw_input is running. raw_input must run in the main
        thread so the terminal is properly restored on CTRL-C.
        The Background IO thread is notified and terminates before the return of this
        function, so no concurrent IO takes place.
    """

    _io_master = self

    class BackgroundIOThread(threading.Thread):
      def __init__(self):
        threading.Thread.__init__(self, name="BackgroundIOThread")
        self.done = False

      def run(self):
        while not self.done:
          # TODO(cs): I believe this may trigger race conditions whenever
          # asynchronous signals preempt the main thread!
          _io_master.select(None)

    # TODO(cs): why do we invoke this sleep?
    self.sleep(0.05)
    io_thread = BackgroundIOThread()
    io_thread.daemon = False
    io_thread.start()
    try:
      return raw_input(prompt)
    finally:
      """ make sure background IO is terminated gracefully before returning """
      io_thread.done = True
      self._ping()
      io_thread.join()

  def _ping(self):
    if self.pinger:
      self.pinger.ping()

  def close_all(self):
    if self._in_select > 0:
      self._close_requested = True
      self._ping()
    else:
      self._do_close_all()

  def _do_close_all(self):
    for w in list(self._workers):
      try:
        w.close()
      except Exception as e:
        log.warn("Error closing IOWorker %s: %s (%d)", w, e.strerror, e.errno)

    if time.sleep is self.sleep:
      time.sleep = self.original_time_sleep

    if (self.pinger):
      self.pinger.ping()
      if hasattr(self.pinger, "close"):
        self.pinger.close()
      self.pinger = None

    self.closed = True

  def poll(self):
    self.select(0)

  def sleep(self, timeout):
    ''' invokes select.select continuously for exactly timeout seconds, then returns. '''
    start = time.time()
    while not self.closed:
      elapsed = time.time() - start
      remaining = timeout - elapsed
      if remaining < 0.01:
        break
      self.select(remaining)

  def deschedule_worker(self, io_worker):
    self._workers.discard(io_worker)

  def reschedule_worker(self, io_worker):
    self._workers.add(io_worker)

  def grab_workers_rwe(self):
    # Now grab workers
    read_sockets = list(self._workers) + [ self.pinger ]
    write_sockets = [ worker for worker in self._workers if worker._ready_to_send ]
    exception_sockets = list(self._workers)
    return (read_sockets, write_sockets, exception_sockets)

  def select(self, timeout=0):
    ''' Waits up to timeout seconds, but may return before then if I/O is
    ready. '''
    self._in_select += 1
    try:
      read_sockets, write_sockets, exception_sockets = self.grab_workers_rwe()
      rlist, wlist, elist = select.select(read_sockets, write_sockets, exception_sockets, timeout)
      self.handle_workers_rwe(rlist, wlist, elist)
    except select.error:
      # TODO(cs): this is a hack: file descriptor is closed upon shut
      # down, and select throws up.
      sys.stderr.write("File Descriptor Closed\n")
    except TypeError:
      # Same behavior, error message is:
      # TypeError: argument must be an int, or have a fileno() method.
      sys.stderr.write("File Descriptor Closed\n")
    finally:
      self._in_select -= 1
    if self._in_select == 0 and self._close_requested and not self.closed:
      self._do_close_all()

  def handle_workers_rwe(self, rlist, wlist, elist):
    if self.pinger in rlist:
      self.pinger.pongAll()
      rlist.remove(self.pinger)

    for worker in elist:
      worker.close()
      if worker in self._workers:
        self._workers.discard(worker)

    for worker in rlist:
      try:
        data = worker.socket.recv(self._BUF_SIZE)
        if data:
          worker._push_receive_data(data)
        else:
          log.warn("Closing socket due to empty read")
          worker.close()
          self._workers.discard(worker)
      except socket.error as (s_errno, strerror):
        log.error("Socket error: " + strerror)
        worker.close()
        self._workers.discard(worker)

    for worker in wlist:
      try:
        l = worker.socket.send(worker.send_buf)
        if l > 0:
          worker._consume_send_buf(l)
      except socket.error as (s_errno, strerror):
        if s_errno != errno.EAGAIN:
          log.error("Socket error: " + strerror)
          worker.close()
          self._workers.discard(worker)
