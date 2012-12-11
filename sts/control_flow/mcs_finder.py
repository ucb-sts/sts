'''
An orchestrating control flow that invokes replayer several times to
find the minimal causal set (MCS) of a failure.
'''

from sts.util.console import msg
from sts.util.convenience import timestamp_string
from sts.replay_event import *
from sts.event_dag import EventDag, split_list
import sts.log_processing.superlog_parser as superlog_parser
from sts.input_traces.input_logger import InputLogger

from sts.control_flow.base import ControlFlow, ReplaySyncCallback
from sts.control_flow.replayer import Replayer

import sys
import time
import random
import logging
import json

class MCSFinder(ControlFlow):
  def __init__(self, simulation_cfg, superlog_path_or_dag,
               invariant_check=InvariantChecker.check_correspondence,
               transform_dag=None,
               mcs_trace_path=None, extra_log=None, dump_runtime_stats=False,
               **kwargs):
    super(MCSFinder, self).__init__(simulation_cfg)
    self.sync_callback = None
    self._log = logging.getLogger("mcs_finder")

    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents
      self.dag = EventDag(superlog_parser.parse_path(superlog_path))
    else:
      self.dag = superlog_path_or_dag

    self.invariant_check = invariant_check
    self.transform_dag = transform_dag
    self.mcs_trace_path = mcs_trace_path
    self._extra_log = extra_log
    self._runtime_stats = None
    self.kwargs = kwargs
    if dump_runtime_stats:
      self._runtime_stats = {}

  def log(self, msg):
    ''' Output a message to both self._log and self._extra_log '''
    self._log.info(msg)
    if self._extra_log is not None:
      self._extra_log.write(msg + '\n')

  def simulate(self, check_reproducability=True):
    # inject domain knowledge into the dag
    self.dag.mark_invalid_input_sequences()
    self.dag = self.dag.filter_unsupported_input_types()

    if len(self.dag) == 0:
      raise RuntimeError("No supported input types?")

    if check_reproducability:
      # First, run through without pruning to verify that the violation exists
      if self._runtime_stats is not None:
        self._runtime_stats["replay_start_epoch"] = time.time()
      violations = self.replay(self.dag)
      if self._runtime_stats is not None:
        self._runtime_stats["replay_end_epoch"] = time.time()
      if violations == []:
        self.log("Unable to reproduce correctness violation!")
        sys.exit(5)

      self.log("Violation reproduced successfully! Proceeding with pruning")

    if self._runtime_stats is not None:
      self._runtime_stats["prune_start_epoch"] = time.time()
    self._ddmin(2)
    if self._runtime_stats is not None:
      self._runtime_stats["prune_end_epoch"] = time.time()
      self._dump_runtime_stats()
    msg.interactive("Final MCS (%d elements): %s" %
                    (len(self.dag.input_events),str(self.dag.input_events)))
    if self.mcs_trace_path is not None:
      self._dump_mcs_trace()
    return self.dag.events

  def _ddmin(self, split_ways, precomputed_subsets=None, iteration=0):
    ''' - iteration is the # of times we've replayed (not the number of times
    we've invoked _ddmin)'''
    # This is the delta-debugging algorithm from:
    #   http://www.st.cs.uni-saarland.de/papers/tse2002/tse2002.pdf,
    # Section 3.2
    # TODO(cs): we could do much better if we leverage domain knowledge (e.g.,
    # start by pruning all LinkFailures)
    if split_ways > len(self.dag.input_events):
      self._track_iteration_size(iteration + 1)
      self.log("Done")
      return

    if precomputed_subsets is None:
      precomputed_subsets = set()

    self.log("Checking %d subsets" % split_ways)
    subsets = split_list(self.dag.input_events, split_ways)
    self.log("Subsets: %s" % str(subsets))
    for i, subset in enumerate(subsets):
      new_dag = self.dag.input_subset(subset)
      input_sequence = tuple(new_dag.input_events)
      self.log("Current subset: %s" % str(input_sequence))
      if input_sequence in precomputed_subsets:
        self.log("Already computed. Skipping")
        continue
      precomputed_subsets.add(input_sequence)
      if input_sequence == ():
        self.log("Subset after pruning dependencies was empty. Skipping")
        continue

      iteration += 1
      violation = self._check_violation(new_dag, i, iteration)
      if violation:
        self.dag = new_dag
        return self._ddmin(2, precomputed_subsets=precomputed_subsets,
                           iteration=iteration)

    self.log("No subsets with violations. Checking complements")
    for i, subset in enumerate(subsets):
      new_dag = self.dag.input_complement(subset)
      input_sequence = tuple(new_dag.input_events)
      self.log("Current complement: %s" % str(input_sequence))
      if input_sequence in precomputed_subsets:
        self.log("Already computed. Skipping")
        continue
      precomputed_subsets.add(input_sequence)
      if input_sequence == ():
        self.log("Subset after pruning dependencies was empty. Skipping")
        continue

      iteration += 1
      violation = self._check_violation(new_dag, i, iteration)
      if violation:
        self.dag = new_dag
        return self._ddmin(max(split_ways - 1, 2),
                           precomputed_subsets=precomputed_subsets,
                           iteration=iteration)

    self.log("No complements with violations.")
    if split_ways < len(self.dag.input_events):
      self.log("Increasing granularity.")
      return self._ddmin(min(len(self.dag.input_events), split_ways*2),
                         precomputed_subsets=precomputed_subsets,
                         iteration=iteration)
    self._track_iteration_size(iteration + 1)

  def _track_iteration_size(self, iteration):
    if self._runtime_stats is not None:
      if "iteration_size" not in self._runtime_stats:
        self._runtime_stats["iteration_size"] = {}
      self._runtime_stats["iteration_size"][iteration] = len(self.dag.input_events)

  def _check_violation(self, new_dag, subset_index, iteration):
    ''' Check if there were violations '''
    self._track_iteration_size(iteration)
    violations = self.replay(new_dag)
    if violations == []:
      # No violation!
      # If singleton, this must be part of the MCS
      self.log("No violation in %d'th..." % subset_index)
      return False
    else:
      # Violation in the subset
      self.log("Violation! Considering %d'th" % subset_index)
      return True

  def replay(self, new_dag):
    # Run the simulation forward
    if self.transform_dag:
      new_dag = self.transform_dag(self.simulation_cfg, new_dag)

    # TODO: MCSFinder needs configure Simulation to always let DataplaneEvents pass through
    replayer = Replayer(new_dag, **self.kwargs)
    replayer.simulate(self.simulation_cfg)
    return self.invariant_check(replayer.simulation)

  def _dump_mcs_trace(self):
    # Dump the mcs trace
    input_logger = InputLogger(output_path=self.mcs_trace_path)
    for e in self.dag.events:
      input_logger.log_input_event(e)
    input_logger.close(self.simulation_cfg, skip_mcs_cfg=True)

  def _dump_runtime_stats(self):
    if self._runtime_stats is not None:
      # First compute durations
      if "replay_end_epoch" in self._runtime_stats:
        self._runtime_stats["replay_duration_seconds"] =\
          (self._runtime_stats["replay_end_epoch"] -
           self._runtime_stats["replay_start_epoch"])
      self._runtime_stats["prune_duration_seconds"] =\
        (self._runtime_stats["prune_end_epoch"] -
         self._runtime_stats["prune_start_epoch"])
      # Now write contents to a file
      now = timestamp_string()
      with file("runtime_stats/" + now + ".json", "w") as output:
        json_string = json.dumps(self._runtime_stats)
        output.write(json_string)
