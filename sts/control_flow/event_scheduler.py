import time

from sts.replay_event import *

class DumbEventScheduler(object):

  kwargs = set(['epsilon_ms', 'timeout_seconds', 'sleep_interval_seconds'])

  def __init__(self, simulation, epsilon_seconds=0.0, timeout_seconds=1.0,
               sleep_interval_seconds=0.2):
    self.simulation = simulation
    self.epsilon_seconds = epsilon_seconds
    self.timeout_seconds = timeout_seconds
    self.sleep_interval_seconds = sleep_interval_seconds
    self.last_event = None

  def schedule(self, event):
    if self.last_event:
      rec_delta = (event.time.as_float() - self.last_event.time.as_float()) + self.epsilon_seconds
      if rec_delta > 0:
        log.info("Sleeping for %.0f ms before next event" % (rec_delta * 1000))
        self.simulation.io_master.sleep(rec_delta)

    start = time.time()
    end = start + self.timeout_seconds - 0.01

    log.debug("Waiting for %r (maximum wait time: %.0f ms)" %
          ( event, self.timeout_seconds * 1000) )

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

  kwargs = set(['timeout' 'speedup', 'delay_input_events', 'initial_wait', 'wait_delta'])

  def __init__(self, simulation, timeout=0.5, speedup=1.0, delay_input_events=True, initial_wait=0.5, wait_delta=0):
    self.simulation = simulation
    self.timeout = timeout
    self.speedup = speedup
    self.delay_input_events = delay_input_events
    self.last_real_time = None
    self.last_rec_time = None
    self.initial_wait = initial_wait
    self.wait_delta = wait_delta

  def schedule(self, event):
    if isinstance(event, InputEvent):
      self.inject_input(event)
    else:
      self.wait_for_internal(event)
    self.update_event_time(event)

  def inject_input(self, event):
    if self.delay_input_events:
      wait_time = self.wait_time(event)
      if wait_time > 0.01:
        log.debug("Delaying input_event %r for %.0f ms" %
            ( event , (wait_time) * 1000 ))

        self.simulation.io_master.sleep(wait_time)
    log.debug("Injecting %r", event)
    end = event.time.as_float() + self.timeout
    self._poll_event(event, self.timeout, end)

  def wait_for_internal(self, event):
    timeout = self.wait_time(event) + self.timeout
    start = time.time()
    end = start + timeout - 0.01

    log.debug("Waiting for %r (maximum wait time: %.0f ms)" %
          ( event, timeout * 1000) )
    self._poll_event(event, timeout, end)

  def _poll_event(self, event, timeout, end):
    proceed = False
    while True:
      now = time.time()
      if event.proceed(self.simulation):
        proceed = True
        break
      elif now > end:
        break
      self.simulation.io_master.select(timeout)
    if proceed:
      log.debug("Succcessfully executed %r" % event)
      self.update_event_time(event)
    else:
      log.warn("Timed out waiting for Event %r" % event)

  def update_event_time(self, event):
    """ update events """
    self.last_real_time = time.time()
    self.last_rec_time = event.time

  def wait_time(self, event):
    """ returns how long to wait for an event to occur or be injected. """
    if not self.last_real_time:
      return self.initial_wait

    rec_delta = (event.time.as_float() - self.last_rec_time.as_float()) / self.speedup + self.wait_delta
    real_delta = time.time() - self.last_real_time

    to_wait = rec_delta - real_delta
    if to_wait > 10000:
      raise RuntimeError("to_wait %d ms is way too big for event" %
                         (to_wait, str(event)))
    return max(to_wait, 0)
