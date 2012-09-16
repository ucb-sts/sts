from collections import defaultdict, namedtuple
from input_traces.fingerprints import *

# TODO(cs): move me to another file?
class GodScheduler(object):
  '''
  Models asynchrony: chooses when switches get to process packets from
  controllers. Buffers packets until they are pulled off the buffer and chosen
  by god (control_flow.py) to be processed.
  '''
  def __init__(self):
    # keep around a queue for each switch of pending openflow messages waiting to
    # arrive at the switches.
    # { pending receive -> [(connection, pending ofp)_1, (connection, pending ofp)_2, ...] }
    self.pendingreceive2conn_messages = defaultdict(list)

  def message_waiting(self, pending_receipt):
    '''
    Return whether the pending receipt is available
    '''
    return pending_receipt in self.pendingreceive2conn_messages

  def schedule(self, pending_receive):
    '''
    Cause the switch to process the pending message associated with
    the fingerprint and controller connection.
    '''
    if not self.message_waiting(pending_receive):
      raise ValueError("No such pending message %s" % pending_receive)
    (conn, message) = self.pendingreceive2conn_messages[pending_receive].pop(0)
    # Avoid memory leak:
    if self.pendingreceive2conn_messages[pending_receive] == []:
      del self.pendingreceive2conn_messages[pending_receive]
    conn.allow_message_receipt(message)

  # TODO(cs): make this a factory method that returns DefferedOFConnection objects
  # with bound god_scheduler.insert() method. (much cleaner API + separation of concerns)
  def insert_pending_message(self, dpid, controller_id, ofp_message, conn):
    ''' Called by DefferedOFConnection to insert messages into our buffer '''
    fingerprint = OFFingerprint.from_pkt(ofp_message)
    pending_receive = PendingReceive(dpid, controller_id, fingerprint)
    conn_message = (conn, ofp_message)
    self.pendingreceive2conn_messages[pending_receive].append(conn_message)

  def pending_receives(self):
    ''' Return the message receipts which are waiting to be scheduled '''
    return self.pendingreceive2conn_messages.keys()

PendingReceive = namedtuple('PendingReceive', ['dpid', 'controller_id', 'fingerprint'])
