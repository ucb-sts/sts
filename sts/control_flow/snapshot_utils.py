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
Boiler plate for snapshotting controllers.

See sts/util/socket_mux/pox_monkeypatcher for the full snapshot
protocol description.
'''

from sts.util.io_master import IOMaster
import errno
import socket
import logging
log = logging.getLogger("snapshotter")


class IOWorkerCloner(object):
  ''' Flushes buffers from an io_worker, and later repopulates
  its buffers to the same state at the point of flushing.

  This is a "one-time-use" object, and its methods should not be invoked more
  than once.
  '''
  def __init__(self, io_worker):
    ''' Assumes io_worker.socket is set to blocking '''
    self.io_worker = io_worker
    self.receive_buf = ""
    self.send_buf = ""

  def _drain_socket(self):
    # Read io_worker.socket
    read = ""
    try:
      read = self.io_worker.socket.recv(IOMaster._BUF_SIZE)
    except socket.error, e:
      if (e.errno == errno.EWOULDBLOCK or e.errno == errno.EBUSY):
        pass
      else:
        raise
    return read

  def drain_buffers(self):
    ''' Drain and store the buffers of the wrapped io_worker'''
    # Places where buffering can occur:
    #  - OpenFlowBuffer pending sends/receives
    #  - OFConnection.io_worker.send_buf
    #  - OFConnection.io_worker.receive_buf
    #  - true_io_worker.send_buf
    #  - true_io_worker.receive_buf
    #  - true_io_worker.socket.read()

    # We only need to deal with the latter three places, since the others shouldn't
    # change across snapshots assuming that the simulation is put into
    # "record-only" mode.
    read = self._drain_socket()

    if read:
      self.io_worker._push_receive_data(read)

    self.receive_buf = self.io_worker.receive_buf
    self.io_worker.receive_buf = ""
    self.send_buf= self.io_worker.send_buf
    self.io_worker.send_buf = ""

  def repopulate_buffers(self, new_socket):
    '''
    Close the wrapped io_worker's socket and replace it with new_socket, and bring the
    buffers back to the same state as they were in at the time drain_buffers()
    was invoked.

    Pre: drain_buffers has been called exactly once before.
    '''
    # N.B. we don't close the io_worker, only the socket
    self.io_worker.socket.close()
    self.io_worker.socket = new_socket
    self.io_worker.receive_buf = self.receive_buf
    self.io_worker.send_buf = self.send_buf

class Snapshotter(object):
  ''' Handles snapshotting of a controller.

  This is a "one-time-use" object, and its methods should not be invoked more
  than once.
  '''
  def __init__(self, simulation, controller):
    self.simulation = simulation
    self.controller = controller
    self.io_worker_cloner = None

  def snapshot_controller(self):
    '''
    Drain the mux select's true_io_worker's buffers, and tell the controller
    to snapshot itself.
    '''
    demuxer = self.simulation.get_demuxer_for_server_info(
                                self.controller.config.server_info)
    io_worker = demuxer.true_io_worker
    self.io_worker_cloner = IOWorkerCloner(io_worker)
    self.io_worker_cloner.drain_buffers()
    self.controller.snapshot()

  def snapshot_proceed(self):
    '''
    Close the old mux socket connected to the controller, tell the cloned
    controller to proceed, and repopulate the io_worker's buffers to its state
    at the time snapshot_controller() was invoked.

    pre: snapshot_controller has been invoked
    '''
    new_socket = self.controller.snapshot_proceed()
    self.io_worker_cloner.repopulate_buffers(new_socket)

