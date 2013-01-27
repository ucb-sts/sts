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
import os

def write_runtime_stats(runtime_stats_file, runtime_stats):
  # Now write contents to a file
  now = timestamp_string()

  if runtime_stats_file is None:
    runtime_stats_file = "runtime_stats/" + now + ".json"

  with file(runtime_stats_file, "w") as output:
    json_string = json.dumps(runtime_stats, sort_keys=True, indent=2,
                             separators=(',', ': '))
    output.write(json_string)

class MCSFinder(ControlFlow):
  def __init__(self, simulation_cfg, superlog_path_or_dag,
               invariant_check=None,
               transform_dag=None, end_wait_seconds=0.5,
               mcs_trace_path=None, extra_log=None, runtime_stats_file=None, dump_runtime_stats=True,
               wait_on_deterministic_values=False,
               no_violation_verification_runs=1,
               **kwargs):
    super(MCSFinder, self).__init__(simulation_cfg)
    self.sync_callback = None
    self._log = logging.getLogger("mcs_finder")

    if invariant_check is None:
      # TODO(cs): figure this out automatically from the original config
      raise ValueError("Must specify invariant check manually (for now)")

    if type(superlog_path_or_dag) == str:
      self.superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents
      self.dag = EventDag(superlog_parser.parse_path(self.superlog_path))
    else:
      self.dag = superlog_path_or_dag

    self.invariant_check = invariant_check
    self.transform_dag = transform_dag
    self.mcs_trace_path = mcs_trace_path
    self._extra_log = extra_log
    self.kwargs = kwargs
    self.end_wait_seconds = end_wait_seconds
    self.wait_on_deterministic_values = wait_on_deterministic_values
    # `no' means "number"
    self.no_violation_verification_runs = no_violation_verification_runs
    self._runtime_stats_file = runtime_stats_file
    self._runtime_stats = None
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

  def init_results(self, results_dir):
    self.results_dir = results_dir
    if self._extra_log is None:
      self._extra_log = open("%s/mcs_finder.log" % results_dir, "w")
    if self._runtime_stats_file is None:
      self._runtime_stats_file = "%s/runtime_stats.json" % results_dir
    if self.mcs_trace_path is None:
      self.mcs_trace_path = "%s/mcs.trace"

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
      Replayer.total_replays = 0
      Replayer.total_inputs_replayed = 0

    if self._runtime_stats is not None:
      self._runtime_stats["prune_start_epoch"] = time.time()
    precompute_cache = PrecomputeCache()
    (dag, total_inputs_pruned) = self._ddmin(self.dag, 2, precompute_cache=precompute_cache)
    # Make sure to track the final iteration size
    self._track_iteration_size(total_inputs_pruned)
    self.dag = dag
    if self._runtime_stats is not None:
      self._runtime_stats["prune_end_epoch"] = time.time()
      self._dump_runtime_stats()
    self.log("Final MCS (%d elements):" % len(self.dag.input_events))
    for i in self.dag.input_events:
      self.log(" - %s" % str(i))
    if self.mcs_trace_path is not None:
      self._dump_mcs_trace()
    return self.dag.events

  def _ddmin(self, dag, split_ways, precompute_cache=None, label_prefix=(),
             total_inputs_pruned=0):
    # This is the delta-debugging algorithm from:
    #   http://www.st.cs.uni-saarland.de/papers/tse2002/tse2002.pdf,
    # Section 3.2
    # TODO(cs): we could do much better if we leverage domain knowledge (e.g.,
    # start by pruning all LinkFailures)
    if split_ways > len(dag.input_events):
      self.log("Done")
      return (dag, total_inputs_pruned)

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
      precompute_cache.update(input_sequence)
      if input_sequence == ():
        self.log("Subset after pruning dependencies was empty. Skipping")
        continue

      self._track_iteration_size(total_inputs_pruned)
      violation = self._check_violation(new_dag, i)
      if violation:
        self.log_violation("Subset %s reproduced violation. Subselecting." % subset_label(label))
        total_inputs_pruned += len(dag.input_events) - len(new_dag.input_events)
        return self._ddmin(new_dag, 2, precompute_cache=precompute_cache,
                           label_prefix = label_prefix + (label, ),
                           total_inputs_pruned=total_inputs_pruned)

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
      precompute_cache.update(input_sequence)

      if input_sequence == ():
        self.log("Subset %s after pruning dependencies was empty. Skipping", subset_label(label))
        continue

      self._track_iteration_size(total_inputs_pruned)
      violation = self._check_violation(new_dag, i)
      if violation:
        self.log_violation("Subset %s reproduced violation. Subselecting." % subset_label(label))
        total_inputs_pruned += len(dag.input_events) - len(new_dag.input_events)
        return self._ddmin(new_dag, max(split_ways - 1, 2),
                           precompute_cache=precompute_cache,
                           label_prefix=prefix,
                           total_inputs_pruned=total_inputs_pruned)

    self.log_no_violation("No complements with violations.")
    if split_ways < len(dag.input_events):
      self.log("Increasing granularity.")
      return self._ddmin(dag, min(len(dag.input_events), split_ways*2),
                         precompute_cache=precompute_cache,
                         label_prefix=label_prefix,
                         total_inputs_pruned=total_inputs_pruned)
    return (dag, total_inputs_pruned)

  def _track_iteration_size(self, total_inputs_pruned):
    if self._runtime_stats is not None:
      if "iteration_size" not in self._runtime_stats:
        self._runtime_stats["iteration_size"] = {}
      self._runtime_stats["iteration_size"][Replayer.total_replays] =\
              len(self.dag.input_events) - total_inputs_pruned

  def _check_violation(self, new_dag, subset_index):
    ''' Check if there were violations '''
    # Try no_violation_verification_runs times to see if the bug shows up
    for i in range(0, self.no_violation_verification_runs):
      violations = self.replay(new_dag)

      if violations != []:
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
    self._track_new_internal_events(simulation, replayer)
    # Wait a bit in case the bug takes awhile to happen
    self.log("Sleeping %d seconds after run"  % self.end_wait_seconds)
    time.sleep(self.end_wait_seconds)
    violations = self.invariant_check(simulation)
    simulation.clean_up()
    return violations

  def _track_new_internal_events(self, simulation, replayer):
    ''' Pre: simulation must have been run through a replay'''
    # We always check against internal events that were buffered at the end of
    # the original run (don't want to overcount)
    path = self.superlog_path + ".unacked"
    if not os.path.exists(path):
      log.warn("unacked internal events file from original run does not exists")
      return
    prev_buffered_receives = [ e.pending_receive for e in
                               EventDag(superlog_parser.parse_path(path)).events ]
    new_message_receipts = []
    for p in simulation.god_scheduler.pending_receives():
      if p not in prev_buffered_receives:
        new_message_receipts.append(repr(p))
      else:
        prev_buffered_receives.remove(p)
    new_state_changes = replayer.unexpected_state_changes
    if "new_internal_events" not in self._runtime_stats:
      # { replay iteration -> [string representations new internal events] }
      self._runtime_stats["new_internal_events"] = {}
    self._runtime_stats["new_internal_events"][Replayer.total_replays] =\
        new_state_changes + new_message_receipts
    if "early_internal_events" not in self._runtime_stats:
      # { replay iteration -> [string representations internal events that
      #                        violated causality] }
      self._runtime_stats["early_internal_events"] = {}
    self._runtime_stats["early_internal_events"][Replayer.total_replays] =\
       replayer.early_state_changes

  def _dump_mcs_trace(self):
    # Dump the mcs trace
    input_logger = InputLogger(output_path=self.mcs_trace_path)
    input_logger.open(self.results_dir)
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
      self._runtime_stats["total_inputs_replayed"] = Replayer.total_inputs_replayed
      if self.transform_dag is not None:
        # TODO(cs): assumes that Peeker is the dag transformer
        self._runtime_stats["ambiguous_counts"] = dict(Peeker.ambiguous_counts)
        self._runtime_stats["ambiguous_events"] = dict(Peeker.ambiguous_events)
      self._runtime_stats["peeker"] = self.transform_dag is not None
      self._runtime_stats["config"] = str(self.simulation_cfg)

      write_runtime_stats(self._runtime_stats_file, self._runtime_stats)

# TODO(cs): Hack alert. Shouldn't be a subclass
class EfficientMCSFinder(MCSFinder):
  ''' Exactly the same functionality as MCSFinder, but assumes that
  indeterminate results cannot occur. Worst-case runtime of O(n) as opposed to
  O(n^2) replays. Taken from the predecessor paper:
     http://www.st.cs.uni-saarland.de/publications/files/zeller-esec-1999.pdf
  Section 4
  '''
  def _ddmin(self, dag, carryover_inputs, precompute_cache=None,
             recursion_level=0, label_prefix=(), total_inputs_pruned=0):
    ''' carryover_inputs is the variable "r" from the paper. '''
    # Hack: superclass calls _ddmin with an integer, which doesn't match our
    # API. Translate that to an empty sequence. (we also don't use precompute_cache)
    if type(carryover_inputs) == int:
      carryover_inputs = []

    local_label = lambda i: "%s/%d" % ("l" if i == 0 else "r", recursion_level)
    subset_label = lambda label: ".".join(map(str, label_prefix + ( label, )))
    print_subset = lambda label, s: subset_label(label) + ": "+" ".join(map(lambda e: e.label, s))

    # Base case. Note that atomic_inputs are grouped-together failure/recovery
    # pairs, or normal inputs otherwise.
    if len(dag.atomic_input_events) == 1:
      self.log("Base case %s" % str(dag.input_events))
      return (dag, total_inputs_pruned)

    (left, right) = split_list(dag.atomic_input_events, 2)
    self.log("Subsets:\n"+"\n".join(print_subset(local_label(i), s)
                                    for i, s in enumerate([left,right])))
    # This is: [dag.input_subset(left), dag.input_subset(right)]
    left_right_dag = []

    for i, subsequence in enumerate([left, right]):
      label = local_label(i)
      prefix = label_prefix + (label, )
      new_dag = dag.atomic_input_subset(subsequence)
      self.log("Current subset: %s" % print_subset(label,
                                                   new_dag.atomic_input_events))
      left_right_dag.append(new_dag)
      # We test on subsequence U carryover_inputs
      test_dag = new_dag.insert_atomic_inputs(carryover_inputs)
      self._track_iteration_size(total_inputs_pruned)
      violation = self._check_violation(test_dag, i)
      if violation:
        self.log("Violation found in %dth half. Recursing" % i)
        total_inputs_pruned += len(dag.input_events) - len(new_dag.input_events)
        return self._ddmin(new_dag, carryover_inputs,
                           recursion_level=recursion_level+1,
                           label_prefix=prefix,
                           total_inputs_pruned=total_inputs_pruned)

    self.log("Interference")
    (left_dag, right_dag) = left_right_dag
    self.log("Recursing on left half")
    prefix = label_prefix + ("il/%d" % recursion_level,)
    (left_result,
     total_inputs_pruned) = self._ddmin(left_dag,
                                        right_dag.insert_atomic_inputs(carryover_inputs).atomic_input_events,
                                        recursion_level=recursion_level+1,
                                        label_prefix=prefix,
                                        total_inputs_pruned=total_inputs_pruned)
    self.log("Recursing on right half")
    prefix = label_prefix + ("ir/%d" % recursion_level,)
    (right_result,
     total_inputs_pruned) = self._ddmin(right_dag,
                                        left_dag.insert_atomic_inputs(carryover_inputs).atomic_input_events,
                                        recursion_level=recursion_level+1,
                                        label_prefix=prefix,
                                        total_inputs_pruned=total_inputs_pruned)

    return (left_result.insert_atomic_inputs(right_result.atomic_input_events),
            total_inputs_pruned)

