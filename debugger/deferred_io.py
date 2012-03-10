'''
Created on Feb 25, 2012

@author: rcs
'''
import exceptions
import sys
import errno
import logging
import Queue
import socket

from pox.lib.util import assert_type, makePinger
from pox.lib.recoco import Select, Task
from pox.lib.ioworker.io_worker import IOWorker

log = logging.getLogger()

class DeferredIOWorker(object):
  '''
  Wrapper class for RecocoIOWorkers.
  
  Rather than actually sending/receiving right away, queue the messages.
  Then there are separate methods for actually sending the messages via
  the wrapped io_worker
  '''
  def __init__(self, io_worker):
    self.io_worker = io_worker
    self.io_worker.set_receive_handler(self.io_worker_receive_handler)
    # Thread-safe read and write queues of indefinite length
    self.receive_queue = Queue.Queue()
    self.send_queue = Queue.Queue()
    # Read buffer that we present to clients
    self.receive_buf = ""

  def permit_send(self):
    '''
    deque()s the first element of the write queue, and actually sends it
    across the wire.
    
    raises an exception if the write queue is empty
    '''
    message = self.send_queue.get()
    # TODO: will recoco guarentee in-order delivery of a sequence of these send requests?
    # TODO: do I need to ensure thread-safety? We're crossing thread boundaries here...
    self.io_worker.send(message)

  def send(self, data):
    """ send data from the client side. fire and forget. """
    self.send_queue.put(data)

  def has_pending_sends(self):
    ''' called by the "arbitrator" in charge of deferal '''
    return not self.send_queue.empty()

  def permit_receive(self):
    '''
    deque()s the first element of the read queue, and notifies the client
    that there is data to be read.
    
    raises an exception if the read queue is empty
    '''
    data = self.receive_queue.get()
    self.receive_buf += data
    self.client_receive_handler(self)

  def set_receive_handler(self, block):
    ''' Called by client '''
    self.client_receive_handler = block
    
  def peek_receive_buf(self):
    return self.receive_buf

  def consume_receive_buf(self, l):
    ''' called from the client to consume receive buffer '''
    assert(len(self.receive_buf) >= l)
    self.receive_buf = self.receive_buf[l:]
    
  def io_worker_receive_handler(self, io_worker):
    ''' called from io_worker (after the Select loop pushes onto io_worker) '''
    # Consume everything immediately
    message = io_worker.peek_receive_buf()
    io_worker.consume_receive_buf(len(message))
    self.receive_queue.put(message)
      
  def has_pending_receives(self):
    ''' called by the "arbitrator" in charge of deferal '''
    return not self.receive_queue.empty()
  
  # Delegation functions.
  # TODO: is there a more pythonic way to implement delegation?
  
  def fileno(self):
    return self.io_worker.fileno()

  def close(self):
    return self.io_worker.close()

  @property
  def socket(self):
    return self.io_worker.socket

  def consume_send_buf(self, l):
    return self.io_worker.consume_send_buf(l)
