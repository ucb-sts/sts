import sys
import errno
import logging
import Queue
import select
import socket
import time
import threading

from pox.lib.util import makePinger
from pox.lib.ioworker.io_worker import IOWorker

log = logging.getLogger()

class STSIOWorker(IOWorker):
  """ An IOWorker that works with our IOMaster """
  def __init__(self, socket, on_close):
    IOWorker.__init__(self)
    self.socket = socket
    # (on_close factory method hides details of the Select loop)
    self.on_close = on_close

  def fileno(self):
    """ Return the wrapped sockets' fileno """
    return self.socket.fileno()

  def send(self, data):
    """ send data from the client side. fire and forget. """
    IOWorker.send(self, data)

  def close(self):
    """ Register this socket to be closed. fire and forget """
    # (don't close until Select loop is ready)
    IOWorker.close(self)
    # on_close is a function not a method
    self.on_close(self)

class IOMaster(object):
  """
  an IO handler that handles the select work for our IO worker
  """
  _select_timeout = 5
  _BUF_SIZE = 8192

  def __init__ (self):
    self._workers = set()
    self.pinger = makePinger()

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
      self._workers.discard(worker)

    worker = STSIOWorker(socket, on_close=on_close)
    self._workers.add(worker)
    return worker

  def monkey_time_sleep(self):
    """monkey patches time.sleep to use this io_masters's time.sleep"""
    self.original_time_sleep = time.sleep
    time.sleep = self.sleep

  def raw_input(self, prompt):
    _io_master = self

    class InputThread(threading.Thread):
      def __init__(self):
        threading.Thread.__init__(self, name="InputThread")
        self.result = None

      def run(self):
        self.result = raw_input(prompt)
        _io_master._ping()

    # some time to do io so we don't get too many competing messages
    self.sleep(0.05)
    input_thread = InputThread()
    input_thread.daemon = True
    input_thread.start()

    while(input_thread.result is None):
      self.select(None)

    return input_thread.result

  def _ping(self):
    self.pinger.ping()

  def close_all(self):
    for w in list(self._workers):
      try:
        w.close()
      except Error as e:
        log.warn("Error closing IOWorker %s: %s (%d)", w, e.strerror, e.errno)

    if time.sleep is self.sleep:
      time.sleep = self.original_time_sleep

  def poll(self):
    self.select(0)

  def sleep(self, timeout):
    start = time.time()
    while True:
      elapsed = time.time() - start
      remaining = timeout - elapsed
      if remaining < 0.01:
        break
      self.select(remaining)

  def select(self, timeout=0):
    # Now grab workers
    read_sockets = list(self._workers) + [ self.pinger ]
    write_sockets = [ worker for worker in self._workers if worker._ready_to_send ]
    exception_sockets = list(self._workers)

    rlist, wlist, elist = select.select(read_sockets, write_sockets, exception_sockets, timeout)

    if self.pinger in rlist:
      self.pinger.pongAll()
      rlist.remove(self.pinger)

    for worker in elist:
      worker.close()
      if worker in self._workers:
        self._workers.remove(worker)

    for worker in rlist:
      try:
        data = worker.socket.recv(self._BUF_SIZE)
        worker._push_receive_data(data)
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
