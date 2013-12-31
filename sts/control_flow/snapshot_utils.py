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

def snapshot_controller(simulation, controller):
  '''
  Temporarily remove true_io_worker from MultiplexedSelect to prevent any
  messages from the controller from getting processed, and tell the controller
  to snapshot itself.
  '''
  demuxer = simulation.get_demuxer_for_server_info(controller.config.server_info)
  io_worker = demuxer.true_io_worker
  simulation.mux_select.deschedule_worker(io_worker)
  controller.snapshot()

def snapshot_proceed(simulation, controller):
  '''
  Close the old mux socket connected to the controller, tell the clone to
  proceed, and reschedule the new mux socket.

  pre: snapshot_controller has been invoked
  '''
  demuxer = simulation.get_demuxer_for_server_info(controller.config.server_info)
  io_worker = demuxer.true_io_worker
  # N.B. we don't close the io_worker, only the socket
  io_worker.socket.close()
  new_socket = controller.snapshot_proceed()
  io_worker.socket = new_socket
  simulation.mux_select.reschedule_worker(io_worker)

