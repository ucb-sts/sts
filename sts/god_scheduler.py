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
import sts.replay_event
from pox.lib.revent import Event, EventMixin
from sts.util.convenience import base64_encode
import logging
log = logging.getLogger("god_scheduler")

class PendingMessage(Event):
  def __init__(self, pending_message, b64_packet, send_event=False):
    # TODO(cs): boolean flag is ugly. Should use subclasses, but EventMixin
    # doesn't support addListener() on super/subclasses.
    super(PendingMessage, self).__init__()
    self.pending_message = pending_message
    self.b64_packet = b64_packet
    self.send_event = send_event

# TODO(cs): move me to another file?
class GodScheduler(EventMixin):
  '''
  Models asynchrony: chooses when switches get to process packets from
  controllers. Buffers packets until they are pulled off the buffer and chosen
  by god (control_flow.py) to be processed.
  '''

  _eventMixin_events = set([PendingMessage])

  def __init__(self):
    # keep around a queue for each switch of pending openflow messages waiting to
    # arrive at the switches.
    # { pending receive -> [(connection, pending ofp)_1, (connection, pending ofp)_2, ...] }
    self.pendingreceive2conn_messages = defaultdict(list)
    # { pending send -> [(connection, pending ofp)_1, (connection, pending ofp)_2, ...] }
    self.pendingsend2conn_messages = defaultdict(list)

  def _pass_through_handler(self, message_event):
    ''' handler for pass-through mode '''
    pending_message = message_event.pending_message
    # Pass through
    self.schedule(pending_message)
    # Record
    if message_event.send_event:
      replay_event_class = sts.replay_event.ControlMessageSend
    else:
      replay_event_class = sts.replay_event.ControlMessageReceive

    replay_event = replay_event_class(pending_message.dpid,
                                      pending_message.controller_id,
                                      pending_message.fingerprint,
                                      b64_packet=message_event.b64_packet)
    self.passed_through_events.append(replay_event)

  def set_pass_through(self):
    ''' Cause all message receipts to pass through immediately without being
    buffered'''
    self.passed_through_events = []
    self.addListener(PendingMessage, self._pass_through_handler)

  def unset_pass_through(self):
    '''Unset pass through mode, and return any events that were passed through
    since pass through mode was set'''
    self.removeListener(self._pass_through_handler)
    passed_events = self.passed_through_events
    self.passed_through_events = []
    return passed_events

  def message_receipt_waiting(self, pending_message):
    '''
    Return whether the pending message receive is available
    '''
    return pending_message in self.pendingreceive2conn_messages

  def message_send_waiting(self, pending_message):
    '''
    Return whether the pending send is available
    '''
    return pending_message in self.pendingsend2conn_messages

  def schedule(self, pending_message):
    '''
    Cause the switch to process the pending message associated with
    the fingerprint and controller connection.
    '''
    receive = type(pending_message) == PendingReceive
    if receive:
      if not self.message_receipt_waiting(pending_message):
        raise ValueError("No such pending message %s" % pending_message)
      multiset = self.pendingreceive2conn_messages
    else:
      if not self.message_send_waiting(pending_message):
        raise ValueError("No such pending message %s" % pending_message)
      multiset = self.pendingsend2conn_messages
    (conn, message) = multiset[pending_message].pop(0)
    # Avoid memory leak:
    if multiset[pending_message] == []:
      del multiset[pending_message]
    if receive:
      conn.allow_message_receipt(message)
    else:
      conn.allow_message_send(message)
    return message

  # TODO(cs): make this a factory method that returns DeferredOFConnection objects
  # with bound god_scheduler.insert() method. (much cleaner API + separation of concerns)
  def insert_pending_receipt(self, dpid, controller_id, ofp_message, conn):
    ''' Called by DeferredOFConnection to insert messages into our buffer '''
    fingerprint = OFFingerprint.from_pkt(ofp_message)
    conn_message = (conn, ofp_message)
    pending_receive = PendingReceive(dpid, controller_id, fingerprint)
    self.pendingreceive2conn_messages[pending_receive].append(conn_message)
    b64_packet = base64_encode(ofp_message)
    self.raiseEventNoErrors(PendingMessage(pending_receive, b64_packet))

  # TODO(cs): make this a factory method that returns DeferredOFConnection objects
  # with bound god_scheduler.insert() method. (much cleaner API + separation of concerns)
  def insert_pending_send(self, dpid, controller_id, ofp_message, conn):
    ''' Called by DeferredOFConnection to insert messages into our buffer '''
    fingerprint = OFFingerprint.from_pkt(ofp_message)
    conn_message = (conn, ofp_message)
    pending_send = PendingSend(dpid, controller_id, fingerprint)
    self.pendingsend2conn_messages[pending_send].append(conn_message)
    b64_packet = base64_encode(ofp_message)
    self.raiseEventNoErrors(PendingMessage(pending_send, b64_packet, send_event=True))

  def pending_receives(self):
    ''' Return the message receipts which are waiting to be scheduled '''
    return self.pendingreceive2conn_messages.keys()

  def pending_sends(self):
    ''' Return the message sends which are waiting to be scheduled '''
    return self.pendingsend2conn_messages.keys()

  def flush(self):
    ''' Garbage collect any previous pending messages '''
    num_pending_messages = (len(self.pendingreceive2conn_messages) +
                            len(self.pendingsend2conn_messages))
    if num_pending_messages > 0:
      log.info("Flushing %d pending messages" % num_pending_messages)
    self.pendingreceive2conn_messages = defaultdict(list)
    self.pendingsend2conn_messages = defaultdict(list)

PendingReceive = namedtuple('PendingReceive', ['dpid', 'controller_id', 'fingerprint'])
PendingSend = namedtuple('PendingSend', ['dpid', 'controller_id', 'fingerprint'])
