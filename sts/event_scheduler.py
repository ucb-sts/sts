import time

from sts.replay_event import *

class EventScheduler(object):
  '''an EventWatchers schedules events. It controls their admission, and
  any post-event delay '''

  kwargs = set(['timeout' 'dilation', 'delay_input_events', 'initial_wait'])

  def __init__(self, simulation, timeout=0.5, dilation=1.0, delay_input_events=True, initial_wait=0.5):
    self.simulation = simulation
    self.timeout = timeout
    self.dilation = dilation
    self.delay_input_events = delay_input_events
    self.last_real_time = None
    self.last_rec_time = None
    self.initial_wait = 2.0

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
    result = event.proceed(self.simulation)
    if not result:
      raise AssertionError("proceed for Input Events should always return True")
    return True

  def wait_for_internal(self, event):
    timeout = self.wait_time(event) + self.timeout
    start = time.time()
    end = start + timeout - 0.01

    log.debug("Waiting for %r (maximum wait time: %.0f ms)" %
          ( event, timeout * 1000) )

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

    rec_delta = (event.time.as_float() - self.last_rec_time.as_float()) / self.speedup
    real_delta = time.time() - self.last_real_time

    to_wait = rec_delta - real_delta
    return max(to_wait, 0)
