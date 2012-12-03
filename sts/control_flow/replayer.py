'''
control flow for running the simulation forward.
  - Replayer: takes as input a `superlog` with causal dependencies, and
    iteratively prunes until the MCS has been found
'''

import pox.openflow.libopenflow_01 as of
from sts.topology import BufferedPatchPanel
from sts.traffic_generator import TrafficGenerator
from sts.event_scheduler import EventScheduler
from sts.util.console import msg
from sts.util.convenience import timestamp_string
from sts.replay_event import *
from sts.event_dag import EventDag, PeekingEventDag, split_list
from sts.syncproto.sts_syncer import STSSyncCallback
import sts.log_processing.superlog_parser as superlog_parser
from sts.syncproto.base import SyncTime
from pox.lib.revent import EventMixin, Event
from sts.input_traces.input_logger import InputLogger

from sts.control_flow.base import ControlFlow, ReplaySyncCallback

import sys
import time
import random
import logging
import json
from collections import Counter

log = logging.getLogger("Replayer")

class Replayer(ControlFlow):
  time_epsilon_microseconds = 500

  '''
  Replay events from a `superlog` with causal dependencies, pruning as we go

  To set the wait_time, pass them as keyword args to the
  constructor of this class, which will pass them on to the EventDay object it creates.
  '''
  def __init__(self, superlog_path_or_dag, create_event_scheduler=None,
               switch_init_sleep_seconds=False,
               sync_callback=None, **kwargs):

    if sync_callback is None:
      sync_callback = ReplaySyncCallback(self.get_interpolated_time)

    ControlFlow.__init__(self, sync_callback)
    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents
      self.dag = EventDag(superlog_parser.parse_path(superlog_path))
    else:
      self.dag = superlog_path_or_dag
    self._switch_init_sleep_seconds = switch_init_sleep_seconds
    # compute interpolate to time to be just before first event
    self.compute_interpolated_time(self.dag.events[0])

    if create_event_scheduler:
      self.create_event_scheduler = create_event_scheduler
    else:
      self.create_event_scheduler = \
        lambda simulation: EventScheduler(simulation,
            **{ k: v for k,v in kwargs.items()
                if k in EventScheduler.kwargs })

  def get_interpolated_time(self):
    '''
    During divergence, the controller may ask for the current time more or
    less times than they did in the original run. We control the time, so we
    need to give them some answer. The answers we give them should be
    (i) monotonically increasing, and (ii) between the time of the last
    recorded ("landmark") event and the next landmark event, and (iii)
    as close to the recorded times as possible

    Our temporary solution is to always return the time right before the next
    landmark
    '''
    # TODO(cs): implement Andi's improved time heuristic
    return self.interpolated_time

  def compute_interpolated_time(self, current_event):
    next_time = current_event.time
    just_before_micro = next_time.microSeconds - self.time_epsilon_microseconds
    just_before_micro = max(0, just_before_micro)
    self.interpolated_time = SyncTime(next_time.seconds, just_before_micro)

  def increment_round(self):
    pass

  def simulate(self, simulation, post_bootstrap_hook=None):
    self.simulation = simulation
    self.run_simulation_forward(self.dag, post_bootstrap_hook)

  def run_simulation_forward(self, dag, post_bootstrap_hook=None):
    # Note that bootstrap() flushes any state from previous runs
    self.simulation.bootstrap(self._switch_init_sleep_seconds)
    event_scheduler = self.create_event_scheduler(self.simulation)
    if post_bootstrap_hook is not None:
      post_bootstrap_hook()
    for event in dag.events:
      self.compute_interpolated_time(event)
      event_scheduler.schedule(event)
      self.increment_round()


