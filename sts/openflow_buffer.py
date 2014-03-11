# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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

from collections import defaultdict, namedtuple
from sts.fingerprints.messages import *
from pox.lib.revent import Event, EventMixin
from sts.syncproto.base import SyncTime
from sts.util.convenience import base64_encode
from sts.util.ordered_default_dict import OrderedDefaultDict
import logging
log = logging.getLogger("openflow_buffer")

class PendingMessage(Event):
  def __init__(self, pending_message, b64_packet, time=None, send_event=False):
    # TODO(cs): boolean flag is ugly. Should use subclasses, but EventMixin
    # doesn't support addListener() on super/subclasses.
    super(PendingMessage, self).__init__()
    self.time = time if time else SyncTime.now()
    self.pending_message = pending_message
    self.b64_packet = b64_packet
    self.send_event = send_event

class PendingQueue(object):
  '''Stores pending messages between switches and controllers'''
  ConnectionId = namedtuple('ConnectionId', ['dpid', 'controller_id'])

  def __init__(self):
    # { ConnectionId(dpid, controller_id) -> MessageId -> [conn_message1, conn_message2, ....]
    self.pending = defaultdict(lambda: OrderedDefaultDict(list))

  def insert(self, message_id, conn_message):
    '''' message_id is a fingerprint named tuple, and conn_message is a ConnMessage named tuple'''
    conn_id = ConnectionId(dpid=message_id.dpid, controller_id=message_id.controller_id)
    self.pending[conn_id][message_id].append(conn_message)

  def has_message_id(self, message_id):
    conn_id = ConnectionId(dpid=message_id.dpid, controller_id=message_id.controller_id)
    return message_id in self.pending[conn_id]

  def get_all_by_message_id(self, message_id):
    conn_id = ConnectionId(dpid=message_id.dpid, controller_id=message_id.controller_id)
    return self.pending[conn_id][message_id]

  def pop_by_message_id(self, message_id):
    conn_id = ConnectionId(dpid=message_id.dpid, controller_id=message_id.controller_id)
    message_id_map = self.pending[conn_id]
    msg_list = message_id_map[message_id]
    if len(msg_list) == 0:
      raise ValueError("Empty queue for message_id %s" % str(message_id))
    res = msg_list.pop(0)
    if len(msg_list) == 0:
      del message_id_map[message_id]
    if len(message_id_map) == 0:
      del self.pending[conn_id]
    return res

  def conn_ids(self):
    return self.pending.keys()

  def get_message_ids(self, dpid, controller_id):
    conn_id = ConnectionId(dpid=dpid, controller_id=controller_id)
    return self.pending[conn_id].keys()

  def __len__(self):
    return sum( len(msg_list)
        for message_id_map in self.pending.values()
        for msg_list in message_id_map.values() )

  def __iter__(self):
    return (message_id for message_id_map in self.pending.values() for message_id in message_id_map.keys())


# TODO(cs): move me to another file?
class OpenFlowBuffer(EventMixin):
  '''
  Models asynchrony: chooses when switches get to process packets from
  controllers. Buffers packets until they are pulled off the buffer and chosen
  by god (control_flow.py) to be processed.
  '''

  # Packet class matches that should be let through automatically if
  # self.allow_whitelisted_packets is True.
  whitelisted_packet_classes = [("class", "ofp_packet_out", ("data", ("class", "lldp", None))),
                                ("class", "ofp_packet_in",  ("data", ("class", "lldp", None))),
                                ("class", "lldp", None),
                                ("class", "ofp_echo_request", None),
                                ("class", "ofp_echo_reply", None)]

  @staticmethod
  def in_whitelist(packet_fingerprint):
    for match in OpenFlowBuffer.whitelisted_packet_classes:
      if packet_fingerprint.check_match(match):
        return True
    return False

  _eventMixin_events = set([PendingMessage])

  def __init__(self):
    # keep around a queue for each switch of pending openflow messages waiting to
    # arrive at the switches.
    # { ConnectionId(dpid, controller_id) -> pending receive -> [(connection, pending ofp)_1, (connection, pending ofp)_2, ...] }
    self.pending_receives = PendingQueue()
    # { ConnectionId(dpid, controller_id) -> pending send -> [(connection, pending ofp)_1, (connection, pending ofp)_2, ...] }
    self.pending_sends = PendingQueue()
    self._delegate_input_logger = None
    self.pass_through_whitelisted_packets = False
    self.pass_through_sends = False

  def _pass_through_handler(self, message_event):
    ''' handler for pass-through mode '''

    # NOTE(aw): FIRST record event, then schedule execution to maintain causality
    # TODO(cs): figure out a better way to resolve circular dependency
    import sts.replay_event
    message_id = message_event.pending_message
    # Record
    if message_event.send_event:
      replay_event_class = sts.replay_event.ControlMessageSend
    else:
      replay_event_class = sts.replay_event.ControlMessageReceive

    replay_event = replay_event_class(dpid=message_id.dpid,
                                      controller_id=message_id.controller_id,
                                      fingerprint=message_id.fingerprint,
                                      b64_packet=message_event.b64_packet,
                                      time=message_event.time)
    if self._delegate_input_logger is not None:
      # TODO(cs): set event.round somehow?
      self._delegate_input_logger.log_input_event(replay_event)
    else: # TODO(cs): why is this an else:?
      self.passed_through_events.append(replay_event)
    # Pass through
    self.schedule(message_id)

  def set_pass_through(self, input_logger=None):
    ''' Cause all message receipts to pass through immediately without being
    buffered'''
    self.passed_through_events = []
    self._delegate_input_logger = input_logger
    self.addListener(PendingMessage, self._pass_through_handler)

  def pass_through_sends_only(self):
    self.pass_through_sends = True

  def unset_pass_through(self):
    '''Unset pass through mode, and return any events that were passed through
    since pass through mode was set'''
    self.removeListener(self._pass_through_handler)
    passed_events = self.passed_through_events
    self.passed_through_events = []
    return passed_events

  def message_receipt_waiting(self, message_id):
    '''
    Return whether the pending message receive is available
    '''
    return self.pending_receives.has_message_id(message_id)

  def message_send_waiting(self, message_id):
    '''
    Return whether the pending send is available
    '''
    return self.pending_sends.has_message_id(message_id)

  def get_message_receipt(self, message_id):
    # pending receives are (conn, message) pairs. We return the message.
    return self.pending_receives.get_all_by_message_id(message_id)[0][1]

  def get_message_send(self, message_id):
    # pending sends are (conn, message) pairs. We return the message.
    return self.pending_sends.get_all_by_message_id(message_id)[0][1]

  def schedule(self, message_id):
    '''
    Cause the switch to process the pending message associated with
    the fingerprint and controller connection.
    '''
    receive = type(message_id) == PendingReceive
    if receive:
      if not self.message_receipt_waiting(message_id):
        raise ValueError("No such pending message %s" % message_id)
      queue = self.pending_receives
    else:
      if not self.message_send_waiting(message_id):
        raise ValueError("No such pending message %s" % message_id)
      queue = self.pending_sends
    (forwarder, message) = queue.pop_by_message_id(message_id)
    if receive:
      forwarder.allow_message_receipt(message)
    else:
      forwarder.allow_message_send(message)
    return message

  # TODO(cs): make this a factory method that returns DeferredOFConnection objects
  # with bound openflow_buffer.insert() method. (much cleaner API + separation of concerns)
  def insert_pending_receipt(self, dpid, controller_id, ofp_message, conn):
    ''' Called by DeferredOFConnection to insert messages into our buffer '''
    fingerprint = OFFingerprint.from_pkt(ofp_message)
    if self.pass_through_whitelisted_packets and self.in_whitelist(fingerprint):
      conn.allow_message_receipt(ofp_message)
      return
    conn_message = (conn, ofp_message)
    message_id = PendingReceive(dpid, controller_id, fingerprint)
    self.pending_receives.insert(message_id, conn_message)
    b64_packet = base64_encode(ofp_message)
    self.raiseEventNoErrors(PendingMessage(message_id, b64_packet))
    return message_id

  # TODO(cs): make this a factory method that returns DeferredOFConnection objects
  # with bound openflow_buffer.insert() method. (much cleaner API + separation of concerns)
  def insert_pending_send(self, dpid, controller_id, ofp_message, conn):
    ''' Called by DeferredOFConnection to insert messages into our buffer '''
    fingerprint = OFFingerprint.from_pkt(ofp_message)
    if (self.pass_through_sends or
        (self.pass_through_whitelisted_packets and self.in_whitelist(fingerprint))):
      conn.allow_message_send(ofp_message)
      return
    conn_message = (conn, ofp_message)
    message_id = PendingSend(dpid, controller_id, fingerprint)
    self.pending_sends.insert(message_id, conn_message)
    b64_packet = base64_encode(ofp_message)
    self.raiseEventNoErrors(PendingMessage(message_id, b64_packet, send_event=True))
    return message_id

  def conns_with_pending_receives(self):
    ''' Return the named_tuples (dpid, controller_id) of connections that have receive messages pending '''
    return self.pending_receives.conn_ids()

  def conns_with_pending_sends(self):
    ''' Return the named_tuples (dpid, controller_id) of connections that have receive messages pending '''
    return self.pending_sends.conn_ids()

  def get_pending_receives(self, dpid, controller_id):
    ''' Return the message receipts (MessageIDs) that are waiting to be scheduled for conn, in order '''
    return self.pending_receives.get_message_ids(dpid=dpid, controller_id=controller_id)

  def get_pending_sends(self, dpid, controller_id):
    ''' Return the message sends (MessageIDs) that are waiting to be scheduled for conn, in order '''
    return self.pending_sends.get_message_ids(dpid=dpid, controller_id=controller_id)

  def flush(self):
    ''' Garbage collect any previous pending messages '''
    num_pending_messages = (len(self.pending_receives) +
                            len(self.pending_sends))
    if num_pending_messages > 0:
      log.info("Flushing %d pending messages" % num_pending_messages)
    self.pending_receives = PendingQueue()
    self.pending_sends = PendingQueue()

PendingReceive = namedtuple('PendingReceive', ['dpid', 'controller_id', 'fingerprint'])
PendingSend = namedtuple('PendingSend', ['dpid', 'controller_id', 'fingerprint'])
ConnectionId = namedtuple('ConnectionId', ['dpid', 'controller_id'])

