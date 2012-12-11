import time

from sts.replay_event import *

class DumbEventScheduler(object):

  kwargs = set(['wait_delta'])

  def __init__(self, simulation, wait_delta=0.1):
    self.simulation = simulation
    self.wait_delta = wait_delta
    self.last_event = None

  def schedule(self, event):
    if self.last_event:
      rec_delta = (event.time.as_float() - self.last_event.time.as_float()) + self.wait_delta
      if rec_delta > 0:
        log.info("Sleeping for %.0f ms before next event" % (rec_delta * 1000))
        self.simulation.io_master.sleep(rec_delta)

    timeout = 1.0
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
      self.simulation.io_master.select(0.2)
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
    while True:
      result = event.proceed(self.simulation)
      if result:
        break
      self.simulation.io_master.select(0.2)

    # TODO: DataplanePermit event can in fact return False, if the Data Plane Packet
    # in question has not been buffered yet. Figure out how to deal with this.
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

    rec_delta = (event.time.as_float() - self.last_rec_time.as_float()) / self.speedup + self.wait_delta
    real_delta = time.time() - self.last_real_time

    to_wait = rec_delta - real_delta
    if to_wait > 10000:
      raise RuntimeError("to_wait %d ms is way too big for event" %
                         (to_wait, str(event)))
    return max(to_wait, 0)
