'''
Created on Mar 8, 2012

@author: rcs
'''

import itertools
import os.path
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), *itertools.repeat("..", 3)))

from pox.lib.mock_socket import MockSocket
from pox.lib.ioworker.io_worker import IOWorker
from debugger.deferred_io import DeferredIOWorker
from nose.tools import eq_

class DeferredIOWorkerTest(unittest.TestCase):
  def test_not_sent_until_permitted(self):
    i = DeferredIOWorker(IOWorker())
    i.send("foo")
    self.assertFalse(i.ready_to_send)
    self.assertFalse(i.send_queue.empty())
    i.permit_send()
    self.assertTrue(i.ready_to_send)
    self.assertTrue(i.send_queue.empty())
    i.consume_send_buf(3)
    self.assertFalse(i.ready_to_send)

  def test_not_received_until_permitted(self):
    i = DeferredIOWorker(IOWorker())
    self.data = None
    def d(worker):
      self.data = worker.peek_receive_buf()
    i.set_receive_handler(d)
    i.push_receive_data("bar")
    self.assertEqual(self.data, None)
    i.permit_receive()
    self.assertEqual(self.data, "bar")
    # d does not consume the data
    i.push_receive_data("hepp")
    i.permit_receive()
    self.assertEqual(self.data, "barhepp")

  def test_receive_consume(self):
    i = DeferredIOWorker(IOWorker())
    self.data = None
    def consume(worker):
      self.data = worker.peek_receive_buf()
      worker.consume_receive_buf(len(self.data))
    i.set_receive_handler(consume)
    i.push_receive_data("bar")
    self.assertEqual(self.data, None)
    i.permit_receive()
    self.assertEqual(self.data, "bar")
    # data has been consumed
    i.push_receive_data("hepp")
    i.permit_receive()
    self.assertEqual(self.data, "hepp")