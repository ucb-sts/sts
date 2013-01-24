'''
An orchestrating control flow that invokes replayer several times to
find the minimal causal set (MCS) of a failure.
'''

from sts.util.console import msg, color
from sts.util.convenience import timestamp_string
from sts.util.precompute_cache import PrecomputeCache, PrecomputePowerSetCache
from sts.replay_event import *
from sts.event_dag import EventDag, split_list
import sts.log_processing.superlog_parser as superlog_parser
from sts.input_traces.input_logger import InputLogger

from sts.control_flow.base import ControlFlow, ReplaySyncCallback
from sts.control_flow.replayer import Replayer
from sts.control_flow.peeker import Peeker

import itertools
import sys
import time
import random
import logging
import json

class MCSFinder(ControlFlow):
  def __init__(self, simulation_cfg, superlog_path_or_dag,
               invariant_check=InvariantChecker.check_correspondence,
               transform_dag=None, end_wait_seconds=0.5,
               mcs_trace_path=None, extra_log=None, dump_runtime_stats=True,
               wait_on_deterministic_values=False,
               no_violation_verification_runs=1,
               ignore_powersets = False,
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
    self.end_wait_seconds = end_wait_seconds
    self.wait_on_deterministic_values = wait_on_deterministic_values
    self.no_violation_verification_runs = no_violation_verification_runs
    self.ignore_powersets = ignore_powersets
    if dump_runtime_stats:
      self._runtime_stats = {}

  def log(self, s):
    ''' Output a message to both self._log and self._extra_log '''
    msg.mcs_event(s)
    if self._extra_log is not None:
      self._extra_log.write(s + '\n')
      self._extra_log.flush()

  def log_violation(self, s):
    ''' Output a message to both self._log and self._extra_log '''
    msg.mcs_event(color.RED + s)
    if self._extra_log is not None:
      self._extra_log.write(s + '\n')
      self._extra_log.flush()

  def log_no_violation(self, s):
    ''' Output a message to both self._log and self._extra_log '''
    msg.mcs_event(color.GREEN + s)
    if self._extra_log is not None:
      self._extra_log.write(s + '\n')
      self._extra_log.flush()

  def simulate(self, check_reproducability=True):
    if self._runtime_stats is not None:
      self._runtime_stats["total_inputs"] = len(self.dag.input_events)
      self._runtime_stats["total_events"] = len(self.dag)
      self._runtime_stats["original_duration_seconds"] =\
        self.dag.events[-1].time.as_float() - self.dag.events[0].time.as_float()

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
        msg.fail("Unable to reproduce correctness violation!")
        sys.exit(5)

      self.log("Violation reproduced successfully! Proceeding with pruning")

    if self._runtime_stats is not None:
      self._runtime_stats["prune_start_epoch"] = time.time()
    if self.ignore_powersets:
      self.precompute_cache = PrecomputePowerSetCache()
    else:
      self.precompute_cache = PrecomputeCache()
    self.dag = self._ddmin(self.dag, 2, precompute_cache=self.precompute_cache)
    if self._runtime_stats is not None:
      self._runtime_stats["prune_end_epoch"] = time.time()
      self._dump_runtime_stats()
    msg.interactive("Final MCS (%d elements): %s" %
                    (len(self.dag.input_events),str(self.dag.input_events)))
    if self.mcs_trace_path is not None:
      self._dump_mcs_trace()
    return self.dag.events

  def _ddmin(self, dag, split_ways, precompute_cache=None, iteration=0, label_prefix=()):
    ''' - iteration is the # of times we've replayed (not the number of times
    we've invoked _ddmin)'''
    # This is the delta-debugging algorithm from:
    #   http://www.st.cs.uni-saarland.de/papers/tse2002/tse2002.pdf,
    # Section 3.2
    # TODO(cs): we could do much better if we leverage domain knowledge (e.g.,
    # start by pruning all LinkFailures)
    if split_ways > len(dag.input_events):
      self._track_iteration_size(dag, iteration + 1, split_ways)
      self.log("Done")
      return dag

    local_label = lambda i, inv=False: "%s%d/%d" % ("~" if inv else "", i, split_ways)
    subset_label = lambda label: ".".join(map(str, label_prefix + ( label, )))
    print_subset = lambda label, s: subset_label(label) + ": "+" ".join(map(lambda e: e.label, s))

    subsets = split_list(dag.input_events, split_ways)
    self.log("Subsets:\n"+"\n".join(print_subset(local_label(i), s) for i, s in enumerate(subsets)))
    for i, subset in enumerate(subsets):
      label = local_label(i)
      new_dag = dag.input_subset(subset)
      input_sequence = tuple(new_dag.input_events)
      self.log("Current subset: %s" % print_subset(label, input_sequence))
      if precompute_cache.already_done(input_sequence):
        self.log("Already computed. Skipping")
        continue
      if input_sequence == ():
        self.log("Subset after pruning dependencies was empty. Skipping")
        continue

      iteration += 1
      self._track_iteration_size(new_dag, iteration, split_ways)
      violation = self._check_violation(new_dag, i)
      if violation:
        self.log_violation("Subset %s reproduced violation. Subselecting." % subset_label(label))
        return self._ddmin(new_dag, 2, precompute_cache=precompute_cache,
                           iteration=iteration, label_prefix = label_prefix + (label, ))
      else:
        # only put elements in the precompute cache that haven't triggered violations
        precompute_cache.update(input_sequence)

    self.log_no_violation("No subsets with violations. Checking complements")
    for i, subset in enumerate(subsets):
      label = local_label(i, True)
      prefix = label_prefix + (label, )
      new_dag = dag.input_complement(subset)
      input_sequence = tuple(new_dag.input_events)
      self.log("Current complement: %s" % print_subset(label, input_sequence))
      if precompute_cache.already_done(input_sequence):
        self.log("Already computed. Skipping")
        continue
      if input_sequence == ():
        self.log("Subset %s after pruning dependencies was empty. Skipping", subset_label(label))
        continue

      iteration += 1
      self._track_iteration_size(new_dag, iteration, split_ways)
      violation = self._check_violation(new_dag, i)
      if violation:
        self.log_violation("Subset %s reproduced violation. Subselecting." % subset_label(label))
        return self._ddmin(new_dag, max(split_ways - 1, 2),
                           precompute_cache=precompute_cache,
                           iteration=iteration, label_prefix=prefix)
      else:
        # only put elements in the precompute cache that haven't triggered violations
        precompute_cache.update(input_sequence)

    self.log_no_violation("No complements with violations.")
    if split_ways < len(dag.input_events):
      self.log("Increasing granularity.")
      return self._ddmin(dag, min(len(self.dag.input_events), split_ways*2),
                         precompute_cache=precompute_cache,
                         iteration=iteration, label_prefix=label_prefix)
    self._track_iteration_size(dag, iteration + 1, split_ways)
    return dag

  def _track_iteration_size(self, dag, iteration, split_ways):
    if self._runtime_stats is not None:
      if "iteration_size" not in self._runtime_stats:
        self._runtime_stats["iteration_size"] = {}
      self._runtime_stats["iteration_size"][iteration] = len(dag.input_events)
      if "split_ways" not in self._runtime_stats:
        self._runtime_stats["split_ways"] = set()
        self._runtime_stats["split_ways"].add(split_ways)

  def _check_violation(self, new_dag, subset_index):
    ''' Check if there were violations '''
    for i in range(0, self.no_violation_verification_runs):
      violations = self.replay(new_dag)

      if not (violations == []):
        # Violation in the subset
        self.log_violation("Violation! Considering %d'th" % subset_index)
        return True

    # No violation!
    self.log_no_violation("No violation in %d'th..." % subset_index)
    return False

  def replay(self, new_dag):
    # Run the simulation forward
    if self.transform_dag:
      new_dag = self.transform_dag(new_dag)

    # TODO(aw): MCSFinder needs to configure Simulation to always let DataplaneEvents pass through
    replayer = Replayer(self.simulation_cfg, new_dag,
                        wait_on_deterministic_values=self.wait_on_deterministic_values,
                        #auto_permit_dp_events=True,
                        **self.kwargs)
    simulation = replayer.simulate()
    # Wait a bit in case the bug takes awhile to happen
    time.sleep(self.end_wait_seconds)
    violations = self.invariant_check(simulation)
    simulation.clean_up()
    return violations

  def _dump_mcs_trace(self):
    # Dump the mcs trace
    input_logger = InputLogger(output_path=self.mcs_trace_path)
    for e in self.dag.events:
      input_logger.log_input_event(e)
    input_logger.close(self, self.simulation_cfg, skip_mcs_cfg=True)

  def _dump_runtime_stats(self):
    if self._runtime_stats is not None:
      # First compute durations
      if "replay_end_epoch" in self._runtime_stats:
        self._runtime_stats["replay_duration_seconds"] =\
          (self._runtime_stats["replay_end_epoch"] -
           self._runtime_stats["replay_start_epoch"])
      if "prune_end_epoch" in self._runtime_stats:
        self._runtime_stats["prune_duration_seconds"] =\
          (self._runtime_stats["prune_end_epoch"] -
           self._runtime_stats["prune_start_epoch"])
      self._runtime_stats["total_replays"] = Replayer.total_replays
      self._runtime_stats["total_inputs_replayed"] =\
          Replayer.total_inputs_replayed
      if self.transform_dag is not None:
        # TODO(cs): assumes that Peeker is the dag transformer
        self._runtime_stats["ambiguous_counts"] =\
            dict(Peeker.ambiguous_counts)
        self._runtime_stats["ambiguous_events"] =\
            dict(Peeker.ambiguous_events)
      self._runtime_stats["config"] = str(self.simulation_cfg)
      self._runtime_stats["peeker"] = self.transform_dag is not None
      self._runtime_stats["split_ways"] = list(self._runtime_stats["split_ways"])
      # Now write contents to a file
      now = timestamp_string()
      with file("runtime_stats/" + now + ".json", "w") as output:
        json_string = json.dumps(self._runtime_stats)
        output.write(json_string)
