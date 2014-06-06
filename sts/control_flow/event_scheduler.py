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

from sts.replay_event import *
import time
from collections import Counter
import operator
import logging

log = logging.getLogger("event_scheduler")

def format_time(time):
  mins = int(time/60)
  secs = int(time % 60)
  ms = int( (time * 1000) % 1000)
  return "%02d:%02d.%03d" % (mins, secs, ms)

class EventSchedulerStats(object):
  def __init__(self):
    # Coarse grained event classes -> match counts
    self.event2matched = Counter()
    # ControlMessageReceive packet classes -> match counts
    self.msgrecv2matched = Counter()
    # ControlMessageSend packet classes -> match counts
    self.msgsend2matched = Counter()
    # Coarse grained event classes -> timeout counts
    self.event2timeouts = Counter()
    # ControlMessageReceive packet classes -> timeout counts
    self.msgrecv2timeouts = Counter()
    # ControlMessageSend packet classes -> timeout counts
    self.msgsend2timeouts = Counter()
    self.replay_start = None
    self.record_start = None

  def start_replay(self, event):
    self.replay_start = time.time()
    self.record_start = event.time.as_float()

  def time(self, event):
    return format_time(time.time() - self.replay_start) + " " + \
           format_time(event.time.as_float() - self.record_start)

  def event_matched(self, event):
    msg.replay_event_success(self.time(event) + " Successfully matched event "+str(event))
    self.event2matched[event.__class__.__name__] += 1
    if event.__class__.__name__ == "ControlMessageReceive":
      pkt_class = event.get_packet().__class__.__name__
      self.msgrecv2matched[pkt_class] += 1
    if event.__class__.__name__ == "ControlMessageSend":
      pkt_class = event.get_packet().__class__.__name__
      self.msgsend2matched[pkt_class] += 1

  def event_timed_out(self, event):
    msg.replay_event_timeout(self.time(event) + " Event timed out "+str(event))
    self.event2timeouts[event.__class__.__name__] += 1
    if event.__class__.__name__ == "ControlMessageReceive":
      pkt_class = event.get_packet().__class__.__name__
      self.msgrecv2timeouts[pkt_class] += 1
    if event.__class__.__name__ == "ControlMessageSend":
      pkt_class = event.get_packet().__class__.__name__
      self.msgsend2timeouts[pkt_class] += 1

  def sorted_match_counts(self):
    for e, count in sorted(self.event2matched.items(),
                           key=operator.itemgetter(1)):
      yield (e, count)

  def sorted_timeout_counts(self):
    for e, count in sorted(self.event2timeouts.items(),
                           key=operator.itemgetter(1)):
      yield (e, count,)

  def get_matches_dict(self):
    d = dict(self.event2matched)
    if 'ControlMessageReceive' in d:
      total = d['ControlMessageReceive']
      d['ControlMessageReceive'] = dict(self.msgrecv2matched)
      d['ControlMessageReceive']['total'] = total
    if 'ControlMessageSend' in d:
      total = d['ControlMessageSend']
      d['ControlMessageSend'] = dict(self.msgsend2matched)
      d['ControlMessageSend']['total'] = total
    return d

  def get_timeouts_dict(self):
    d = dict(self.event2timeouts)
    if 'ControlMessageReceive' in d:
      total = d['ControlMessageReceive']
      d['ControlMessageReceive'] = dict(self.msgrecv2timeouts)
      d['ControlMessageReceive']['total'] = total
    if 'ControlMessageSend' in d:
      total = d['ControlMessageSend']
      d['ControlMessageSend'] = dict(self.msgsend2timeouts)
      d['ControlMessageSend']['total'] = total
    return d

  def __str__(self):
    total_matched = sum(self.event2matched.values())
    total_timeouts = sum(self.event2timeouts.values())
    s = []
    s.append("Events matched: %d, timed out: %d\n" % (total_matched,
                                                      total_timeouts))
    s.append("Matches per event type:\n")
    for e, count in self.sorted_match_counts():
      s.append("  %s %d\n" % (e, count,))
      if e == "ControlMessageReceive":
        for pkt_class, c in self.msgrecv2matched.iteritems():
          s.append("\t\t  %s : %d\n" % (pkt_class, c))
      if e == "ControlMessageSend":
        for pkt_class, c in self.msgsend2matched.iteritems():
          s.append("\t\t  %s : %d\n" % (pkt_class, c))

    s.append("Timeouts per event type:\n")
    for e, count in self.sorted_timeout_counts():
      s.append("  %s %d\n" % (e, count,))
      if e == "ControlMessageReceive":
        for pkt_class, c in self.msgrecv2timeouts.iteritems():
          s.append("\t\t  %s : %d\n" % (pkt_class, c))
      if e == "ControlMessageSend":
        for pkt_class, c in self.msgsend2timeouts.iteritems():
          s.append("\t\t  %s : %d\n" % (pkt_class, c))

    return "".join(s)

class EventSchedulerBase(object):
  def __init__(self):
    self._input_logger = None

  def set_input_logger(self, input_logger):
    self._input_logger = input_logger

  def _log_event(self, event, **kws):
    if self._input_logger is not None:
      self._input_logger.log_input_event(event, **kws)

class DumbEventScheduler(EventSchedulerBase):
  kwargs = set(['epsilon_seconds', 'sleep_interval_seconds'])

  def __init__(self, simulation, epsilon_seconds=0.0, sleep_interval_seconds=0.2):
    super(DumbEventScheduler, self).__init__()
    self.simulation = simulation
    self.epsilon_seconds = epsilon_seconds
    self.sleep_interval_seconds = sleep_interval_seconds
    self.last_event = None
    self.stats = EventSchedulerStats()

  def schedule(self, event):
    if self.last_event:
      rec_delta = (event.time.as_float() - self.last_event.time.as_float())
      if rec_delta > 0:
        log.info("Sleeping for %.0f ms before next event" % (rec_delta * 1000))
        self.simulation.io_master.sleep(rec_delta)
    else:
      self.stats.start_replay(event)

    log.debug("Waiting for %s (maximum wait time: %.0f ms)" %
          ( str(event).replace("\n", ""), self.epsilon_seconds * 1000) )

    now = time.time()
    end = now  + self.epsilon_seconds
    proceed = False
    while True:
      now = time.time()
      if event.proceed(self.simulation):
        proceed = True
        break
      elif now > end:
        break
      self.simulation.io_master.select(self.sleep_interval_seconds)
    if proceed:
      event.timed_out = False
      self.stats.event_matches(event)
    else:
      event.timed_out = True
      self.stats.event_timed_out(event)
    event.replay_time = SyncTime.now()
    self._log_event(event)
    self.last_event = event

class EventScheduler(EventSchedulerBase):
  '''An EventWatcher schedules events. It controls their admission and
  any post-event delay '''

  kwargs = set(['speedup', 'delay_input_events', 'initial_wait',
                'epsilon_seconds', 'sleep_interval_seconds',
                'sleep_continuation', 'select_continuation'])

  def __init__(self, simulation, speedup=1.0, delay_input_events=True,
               initial_wait=0.5, epsilon_seconds=0.5, sleep_interval_seconds=0.2,
               sleep_continuation=None, select_continuation=None, assertion_checking=False):
    super(EventScheduler, self).__init__()
    self.simulation = simulation
    self.speedup = speedup
    self.delay_input_events = delay_input_events
    self.last_real_time = None
    self.last_rec_time = None
    self.initial_wait = initial_wait
    self.epsilon_seconds = epsilon_seconds
    self.sleep_interval_seconds = sleep_interval_seconds
    self.started = False
    self.stats = EventSchedulerStats()
    self.assertion_checking = assertion_checking
    self.sleep_continuation = sleep_continuation
    if sleep_continuation is None:
      self.sleep_continuation = self.simulation.io_master.sleep
    self.select_continuation = select_continuation
    if select_continuation is None:
      self.select_continuation = self.simulation.io_master.select

  def schedule(self, event):
    if not self.started:
      self.stats.start_replay(event)
      self.started = True

    if isinstance(event, InputEvent):
      self.inject_input(event)
    elif isinstance(event, InternalEvent):
      if event.whitelisted():
        self.delay_whitelisted_internal_event(event)
      else:
        self.wait_for_internal(event)
    self.update_event_time(event)
    self._log_event(event)

  def inject_input(self, event):
    if self.delay_input_events:
      wait_time_seconds = self.wait_time(event)
      if wait_time_seconds > 0.01:
        log.debug("Delaying input_event %s for %.0f ms" %
            ( str(event).replace("\n", "") , (wait_time_seconds) * 1000 ))

        self.sleep_continuation(wait_time_seconds)
    log.debug("Injecting %r", event)
    # TODO(cs): AFACT, this is essentially a dummy variable? Since event.time
    # is in the past... Andi, can you verify this?
    end = event.time.as_float()
    self._poll_event(event, end)

  def delay_whitelisted_internal_event(self, event):
    wait_time_seconds = self.wait_time(event)
    log.debug("Event whitelisted %s, just delaying until predicted time %.0f ms)" %
          ( repr(event).replace("\n", ""), wait_time_seconds * 1000) )
    self.sleep_continuation(wait_time_seconds)
    self.stats.event_matched(event)
    self.update_event_time(event)
    event.replay_time = SyncTime.now()

  def wait_for_internal(self, event):
    wait_time_seconds = self.wait_time(event)
    start = time.time()
    # TODO(cs): why - 0.01?
    end = start + wait_time_seconds - 0.01 + self.epsilon_seconds
    if event.timeout_disallowed:
      # Reaallllly far in the future
      end = 30000000000 # Fri, 30 Aug 2920 05:20:00 GMT
      log.debug("Waiting for %s forever" %
                ( repr(event).replace("\n", "")))
    else:
      log.debug("Waiting for %s (maximum wait time: %.0f ms)" %
            ( repr(event).replace("\n", ""), self.epsilon_seconds * 1000) )
    self._poll_event(event, end)

  def _poll_event(self, event, end_time):
    proceed = False
    while True:
      now = time.time()
      if event.proceed(self.simulation):
        proceed = True
        break
      elif now > end_time:
        break
      self.select_continuation(self.sleep_interval_seconds)
    if proceed:
      event.timed_out = False
      self.stats.event_matched(event)
      self.update_event_time(event)
    else:
      event.timed_out = True
      self.stats.event_timed_out(event)
    event.replay_time = SyncTime.now()

  def update_event_time(self, event):
    """ update our bearing on where we currently our in the timeline """
    self.last_real_time = time.time()
    self.last_rec_time = event.time

  def wait_time(self, event):
    """ returns how long to wait in seconds for an event to occur or be injected. """
    if not self.last_real_time:
      return self.initial_wait

    rec_delta = (event.time.as_float() - self.last_rec_time.as_float()) / self.speedup
    real_delta = time.time() - self.last_real_time

    to_wait = rec_delta - real_delta
    if self.assertion_checking and to_wait > 10000:
      raise RuntimeError("to_wait %f ms is way too big for event %s" %
                         (to_wait, str(event)))
    # -0.03 to account for floating point error
    if self.assertion_checking and to_wait < -0.03:
      raise RuntimeError("Wait time %f is negative for event %s" %
                         (to_wait, str(event)))
    return max(to_wait, 0)
