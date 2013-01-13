import time

from sts.replay_event import *

import logging
log = logging.getLogger("event_scheduler")

class DumbEventScheduler(object):

  kwargs = set(['epsilon_seconds', 'sleep_interval_seconds'])

  def __init__(self, simulation, epsilon_seconds=0.0, sleep_interval_seconds=0.2):
    self.simulation = simulation
    self.epsilon_seconds = epsilon_seconds
    self.sleep_interval_seconds = sleep_interval_seconds
    self.last_event = None

  def schedule(self, event):
    if self.last_event:
      rec_delta = (event.time.as_float() - self.last_event.time.as_float())
      if rec_delta > 0:
        log.info("Sleeping for %.0f ms before next event" % (rec_delta * 1000))
        self.simulation.io_master.sleep(rec_delta)

    start = time.time()

    log.debug("Waiting for %s (maximum wait time: %.0f ms)" %
          ( str(event).replace("\n", ""), self.epsilon_seconds * 1000) )

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
      log.debug("Succcessfully executed %r" % event)
    else:
      log.warn("Timed out waiting for Event %r" % event)
    self.last_event = event

class EventScheduler(object):
  '''an EventWatchers schedules events. It controls their admission, and
  any post-event delay '''

  kwargs = set(['speedup', 'delay_input_events', 'initial_wait',
                'epsilon_seconds', 'sleep_interval_seconds'])

  def __init__(self, simulation, speedup=1.0,
               delay_input_events=True, initial_wait=0.5, epsilon_seconds=0.5,
               sleep_interval_seconds=0.2):
    self.simulation = simulation
    self.speedup = speedup
    self.delay_input_events = delay_input_events
    self.last_real_time = None
    self.last_rec_time = None
    self.initial_wait = initial_wait
    self.epsilon_seconds = epsilon_seconds
    self.sleep_interval_seconds = sleep_interval_seconds

  def schedule(self, event):
    if isinstance(event, InputEvent):
      self.inject_input(event)
    else:
      self.wait_for_internal(event)
    self.update_event_time(event)

  def inject_input(self, event):
    if self.delay_input_events:
      wait_time_seconds = self.wait_time(event)
      if wait_time_seconds > 0.01:
        log.debug("Delaying input_event %s for %.0f ms" %
            ( str(event).replace("\n", "") , (wait_time_seconds) * 1000 ))

        self.simulation.io_master.sleep(wait_time_seconds)
    log.debug("Injecting %r", event)
    # TODO(cs): AFACT, this is essentially a dummy variable? Since event.time
    # is in the past... Andi, can you verify this?
    end = event.time.as_float()
    self._poll_event(event, end)

  def wait_for_internal(self, event):
    wait_time_seconds = self.wait_time(event)
    start = time.time()
    # TODO(cs): why - 0.01?
    end = start + wait_time_seconds - 0.01 + self.epsilon_seconds
    if event.timeout_disallowed:
      # Reaallllly far in the future
      end = 30000000000 # Fri, 30 Aug 2920 05:20:00 GMT
      log.debug("Waiting for %s forever" %
                ( str(event).replace("\n", "")))
    else:
      log.debug("Waiting for %s (maximum wait time: %.0f ms)" %
            ( str(event).replace("\n", ""), self.epsilon_seconds * 1000) )
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
      self.simulation.io_master.select(self.sleep_interval_seconds)
    if proceed:
      log.debug("Succcessfully executed %r" % event)
      self.update_event_time(event)
    else:
      log.warn("Timed out waiting for Event %s" % repr(event).replace("\n",""))

  def update_event_time(self, event):
    """ update events """
    self.last_real_time = time.time()
    self.last_rec_time = event.time

  def wait_time(self, event):
    """ returns how long to wait in seconds for an event to occur or be injected. """
    if not self.last_real_time:
      return self.initial_wait

    rec_delta = (event.time.as_float() - self.last_rec_time.as_float()) / self.speedup
    real_delta = time.time() - self.last_real_time

    to_wait = rec_delta - real_delta
    if to_wait > 10000:
      raise RuntimeError("to_wait %d ms is way too big for event %s" %
                         (to_wait, str(event)))
    return max(to_wait, 0)
