# Copyright 2011-2015 Colin Scott
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

'''
Removes events one at a time. Mostly for comparison against MCSFinder (delta
debugging).
'''

# NOTE: this code is highly redundant with mcs_finder.py. But we have
# justification! We are using it to rerun old experiments, where we need to
# roll back the codebase. We then drop in this code to the rolled back
# codebase. For that to work, we need to minimize dependencies, since older
# versions of the code may not have everything we need!

from sts.control_flow.mcs_finder import MCSFinder
from sts.util.convenience import timestamp_string, mkdir_p, ExitCode


from collections import Counter
import copy
import sys
import time
import random
import logging
import json
import os
import re

class OneAtATimeRemoval(MCSFinder):
  # N.B. only called in the parent process.
  def simulate(self, check_reproducibility=True):
    self._runtime_stats.set_dag_stats(self.dag)

    # apply domain knowledge: treat failure/recovery pairs atomically, and
    # filter event types we don't want to include in the MCS
    # (e.g. CheckInvariants)
    self.dag.mark_invalid_input_sequences()
    # TODO(cs): invoke dag.filter_unsupported_input_types()

    if len(self.dag) == 0:
      raise RuntimeError("No supported input types?")

    # if check_reproducibility:
    #   # First, run through without pruning to verify that the violation exists
    #   self._runtime_stats.record_replay_start()

    #   (bug_found, i) = self.replay_max_iterations(self.dag, "reproducibility",
    #                                               ignore_runtime_stats=True)
    #   self._runtime_stats.set_initial_verification_runs_needed(i)
    #   self._runtime_stats.record_replay_end()
    #   if not bug_found:
    #     msg.fail("Unable to reproduce correctness violation!")
    #     sys.exit(5)
    #   self.log("Violation reproduced successfully! Proceeding with pruning")

    # self._runtime_stats.record_prune_start()

    # Invoke delta debugging
    (dag, total_inputs_pruned) = self.minimize(self.dag)
    # Make sure to track the final iteration size
    self._track_iteration_size(total_inputs_pruned)
    self.dag = dag

    self._runtime_stats.record_prune_end()
    self.mcs_log_tracker.dump_runtime_stats()

    if self.replay_final_trace:
      #  Replaying the final trace achieves two goals:
      #  - verifies that the MCS indeed ends in the violation
      #  - allows us to prune internal events that time out
      (bug_found, i) = self.replay_max_iterations(self.dag, "final_mcs_trace",
                                                  ignore_runtime_stats=True)
      if not bug_found:
        self.log('''Warning: MCS did not result in violation. Trying replay '''
                 '''again without timed out events.''')
        # TODO(cs): always replay the MCS without timeouts, since the console
        # output will be significantly cleaner?
        no_timeouts = self.dag.filter_timeouts()
        (bug_found, i) = self.replay_max_iterations(no_timeouts, "final_mcs_no_timed_out_events",
                                                    ignore_runtime_stats=True)
        if not bug_found:
          self.log('''Warning! Final MCS did not result in violation, even '''
                   '''after ignoring timed out internal events. Your run ''
                   '' is probably effected by non-determinism.\n'''
                   '''Try setting MCSFinder's max_replays_per_subsequence '''
                   '''parameter in your config file (e.g. max_replays_per_subsequence=10)\n'''
                   '''If that still doesn't work, see tools/visualization/visualize1D.html '''
                   '''for debugging''')

    self.log("=== Total replays: %d ===" % self._runtime_stats.total_replays)
    self.log("Final MCS (%d elements):" % len(self.dag.input_events))
    for i in self.dag.input_events:
      self.log(" - %s" % str(i))

    # N.B. dumping the MCS trace must occur after the final replay trace,
    # since we need to infer which events will time out for events.trace.notimeouts
    if self.mcs_trace_path is not None:
      self.mcs_log_tracker.dump_mcs_trace(self.dag, self)
    return ExitCode(0)

  # N.B. always called by the parent process.
  def minimize(self, dag):
    total_inputs_pruned = 0

    for event in list(dag.atomic_input_events()):
      label = event.label
      print "Trying removal of", str(event)
      # Somewhat awkward: there is an atomic_input_subset method but not a
      # atomic_input_complement method. So we compute the atomic complement ourselves.
      new_dag = dag.input_complement(dag.atomic_input_subset([event]).input_events)
      self._track_iteration_size(total_inputs_pruned)
      violation = self._check_violation(new_dag, i, label)
      if violation:
        self.log_violation("Event %s reproduced violation. Subselecting." % label)
        try:
          self.mcs_log_tracker.maybe_dump_intermediate_mcs(total_inputs_pruned, new_dag,
                                                           label, self)
        except:
          # earlier versions had arity=3
          self.mcs_log_tracker.maybe_dump_intermediate_mcs(new_dag, label, self)

        total_inputs_pruned += len(dag.input_events) - len(new_dag.input_events)
        dag = new_dag
    return (dag, total_inputs_pruned)

