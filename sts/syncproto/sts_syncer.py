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

# This is STS's end of the sync protocol. Listens to all controller-specific
# syncers and dispatches messages to STS handlers.

from sts.syncproto.base import SyncProtocolSpeaker, SyncMessage, SyncTime, SyncIODelegate

from pox.lib.util import parse_openflow_uri, connect_socket_with_backoff

import logging
log = logging.getLogger("sts_sync_proto")

class STSSyncProtocolSpeaker(SyncProtocolSpeaker):
  def __init__(self, controller, state_master, io_delegate):
    if state_master is None:
      raise ValueError("state_master is null")

    self.state_master = state_master
    self.controller = controller

    handlers = {
        ("ASYNC", "StateChange"): self._log_async_state_change,
        ("SYNC", "StateChange"): self._log_sync_state_change,
        ("REQUEST", "DeterministicValue"): self._get_deterministic_value
    }
    SyncProtocolSpeaker.__init__(self, handlers, io_delegate)

  def _log_async_state_change(self, message):
    self.state_master.state_change("ASYNC", message.xid, self.controller, message.time, message.fingerPrint, message.name, message.value)

  def _log_sync_state_change(self, message):
    # Note: control_flow needs to register a handler on state_master to ACK the
    # controller
    self.state_master.state_change("SYNC", message.xid, self.controller, message.time, message.fingerPrint, message.name, message.value)

  def _get_deterministic_value(self, message):
    self.state_master.get_deterministic_value(self.controller, message.name,
                                              message.xid)

class STSSyncConnection(object):
  """ A connection to a controller with the sts sync protocol """
  def __init__(self, controller, state_master, sync_uri):
    self.controller = controller
    (self.mode, self.host, self.port) = parse_openflow_uri(sync_uri)
    if state_master is None:
      raise ValueError("state_master is null")
    self.state_master = state_master
    self._on_disconnect = []
    self.io_worker = None
    self.speaker = None

  def on_disconnect(self, func):
    self._on_disconnect.append(func)

  def connect(self, io_master):
    if self.mode != "tcp":
      raise RuntimeError("only tcp (active) mode supported by now")

    socket = connect_socket_with_backoff(self.host, self.port)
    self.io_delegate = SyncIODelegate(io_master, socket)
    self.speaker = STSSyncProtocolSpeaker(controller=self.controller,
        state_master=self.state_master, io_delegate=self.io_delegate)

  def disconnect(self):
    if(self.io_worker):
      self.io_worker.close()
    for handler in self._on_disconnect:
      handler(self)

  def close(self):
    self.disconnect()

  def get_nom_snapshot(self):
    if self.speaker:
      return self.speaker.sync_request("NOMSnapshot", "", timeout=10)
    else:
      log.warn("STSSyncConnection: not connected. cannot handle requests")

  def send_link_notification(self, link_attrs):
    # Link attrs must be a list of the form:
    # [dpid1, port1, dpid2, port2]
    if self.speaker:
      msg = SyncMessage(type="ASYNC", messageClass="LinkDiscovery",
                        value=link_attrs)
      return self.speaker.send(msg)
    else:
      log.warn("STSSyncConnection: not connected. cannot send link")

  def ack_sync_notification(self, messageClass, xid):
    if self.speaker:
      return self.speaker.ack_sync_notification(messageClass, xid)
    else:
      log.warn("STSSyncConnection: not connected. cannot ACK")

  def send_deterministic_value(self, xid, value):
    if self.speaker:
      msg = SyncMessage(type="RESPONSE", messageClass="DeterministicValue",
                        time=value, xid=xid, value=value)
      return self.speaker.send(msg)
    else:
      log.warn("STSSyncConnection: not connected. cannot ACK")

class STSSyncConnectionManager(object):
  """the connection manager for the STS sync protocols.
     TODO: finish"""
  def __init__(self, io_master, state_master):
    self.io_master  = io_master
    self.sync_connections = []
    if state_master is None:
      raise ValueError("state_master is null")
    self.state_master = state_master

  def connect(self, controller, sync_uri):
    s = STSSyncConnection(controller=controller, state_master=self.state_master, sync_uri=sync_uri)
    s.connect(self.io_master)
    s.on_disconnect(self.remove_connection)

    self.sync_connections.append(s)

    return s

  def remove_connection(self, connection):
    if connection in self.sync_connections:
      self.sync_connections.remove(connection)

class STSSyncCallback(object):
  """ override with your favorite functionality """
  def state_change(self, type, controller, time, fingerprint, name, value):
    log.info("{}: controller: {} time: {} fingerprint: {} name: {} value: {}"\
             .format(type, controller, time, fingerprint, name, value))
  def get_deterministic_value(self, controller, name):
    if name == "gettimeofday":
      return SyncTime.now()
