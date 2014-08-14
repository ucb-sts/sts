# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2014      Ahmed El-Hassany
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

import logging
import sys
import time

from sts.replay_event import CheckInvariants
from sts.replay_event import InvariantViolation

from sts.syncproto.base import SyncTime
from sts.control_flow.base import ControlFlow
from config.invariant_checks import name_to_invariant_check

from sts.util.console import msg


LOG = logging.getLogger("sts.control_flow.events_exec")


class EventsExec(ControlFlow):
  def __init__(self, simulation, events_generator, check_interval=None,
               delay=0.1,
               steps=None, input_logger=None,
               invariant_check_name="InvariantChecker.check_correspondence",
               halt_on_violation=False, log_invariant_checks=True,):
    """
    Options:
      - simulation:
      - events_generator:
      - check_interval: the period for checking invariants, in terms of
                        logical rounds
      - delay: how long to sleep between each logical round
      - steps: how many logical rounds to execute, None for infinity
      - input_logger: None, or a InputLogger instance
      - invariant_check_name: the name of the invariant check, from
                              config/invariant_checks.py
      - halt_on_violation: whether to stop after a bug has been detected
      - log_invariant_checks: whether to log InvariantCheck events
    """
    ControlFlow.__init__(self, simulation)
    self.simulation = simulation
    self.log = LOG
    self.events_generator = events_generator
    self.check_interval = check_interval
    if self.check_interval is None:
      self.log.warn("EventsExec Warning: Check interval is not specified..."
                    " not checking invariants")
    if invariant_check_name not in name_to_invariant_check:
      raise ValueError("Unknown invariant check %s.\n"
                       "Invariant check name must be defined in "
                       "config.invariant_checks",
                       invariant_check_name)
    self.invariant_check_name = invariant_check_name
    self.invariant_check = name_to_invariant_check[invariant_check_name]

    # Make execution deterministic to allow the user to easily replay
    self.log_invariant_checks = log_invariant_checks
    self.delay = delay
    self.steps = steps
    self._input_logger = input_logger
    self.logical_time = 0
    self.halt_on_violation = halt_on_violation


  def init_results(self, results_dir):
    """Set up event log files"""
    if self._input_logger:
      self._input_logger.open(results_dir)
    # TODO(AH): copy params

  def _log_input_event(self, event, **kws):
    self.log.debug("Logging event: %s", event)
    if self._input_logger is not None:
      event.round = self.logical_time
      self._input_logger.log_input_event(event, **kws)

  def simulate(self):
    self.loop()

  def loop(self):
    if self.steps:
      end_time = self.logical_time + self.steps
    else:
      end_time = sys.maxint

    while self.logical_time < end_time:
      self.logical_time += 1
      self.log.info("In round: %d", self.logical_time)
      events = self.events_generator.next_events(self.logical_time)
      # Treat events as autonomous
      for event in events:
        # Set the time and round for each event
        event.round = self.logical_time
        event.time = SyncTime.now()
        self._log_input_event(event)
        event_ret = event.proceed(self.simulation)
        self.log.info("Return result for event '%s': %s", event, event_ret)
      halt = self.maybe_check_invariant()
      if halt and self.halt_on_violation:
        break
      time.sleep(self.delay)

  def maybe_check_invariant(self):
    if (self.check_interval is not None and
        (self.logical_time % self.check_interval) == 0):
      # Time to run correspondence!
      # TODO(cs): may need to revert to threaded version if runtime is too
      # long
      def do_invariant_check():
        self.log.debug("Checking invariant: %s", self.invariant_check_name)
        if self.log_invariant_checks:
          self._log_input_event(CheckInvariants(round=self.logical_time,
                                 invariant_check_name=self.invariant_check_name))

        violations = self.invariant_check(self.simulation)
        self.simulation.violation_tracker.track(violations, self.logical_time)
        persistent_violations = self.simulation.violation_tracker.persistent_violations
        transient_violations = list(set(violations) - set(persistent_violations))

        if violations != []:
          msg.fail("The following correctness violations have occurred: %s,"
                   "Check name: %s" % (str(violations), self.invariant_check_name))
        else:
          msg.success("No correctness violations!")
        if transient_violations != []:
          self._log_input_event(InvariantViolation(transient_violations))
        if persistent_violations != []:
          msg.fail("Persistent violations detected!: %s"
                   % str(persistent_violations))
          self._log_input_event(InvariantViolation(persistent_violations, persistent=True))
          if self.halt_on_violation:
            return True
      return do_invariant_check()
