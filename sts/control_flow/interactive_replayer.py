# Copyright 2011-2013 Colin Scott
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
Motivation for this tool:

Even with a perfectly minimized trace, the human still needs to
understand what was going on. This tool allows them to step through
the series of network configurations interactively. This might
specifically help them to:
  - visualize the network topology
  - trace the series of link/switch failures/recoveries
  - trace the series of host migrations
  - trace the series of flow_mods
  - trace the series of traffic injections
  - perturb the original event sequence by adding / removing inputs
    interactively
  - trace the series of link discoveries (TBD)
'''
# TODO(cs): automatically print formatted tables showing those traces, just as I did
# on paper while tracking down the root cause of the NOX loop.

from sts.control_flow.base import *
from sts.control_flow.interactive import *
import sts.input_traces.log_parser as log_parser
from sts.replay_event import *
from sts.event_dag import EventDag
from sts.util.console import msg

import logging
log = logging.getLogger("interactive_replayer")

# TODO(cs): our switches call time.time() to decide when to expire flow
# entries. This is potentially problematic, since we interactive mode perturbs
# time substantially!

# TODO(cs): support DataplanePermit/DataplaneDrop. This would require a change
# in how we wait for internal events (the only other internal event we
# currently support it ControlMessageReceive, which we inject manually rather
# than waiting for).

class InteractiveReplayer(Interactive):
  '''
  Presents an interactive prompt for replaying an event trace, allowing the
  user to examine the series of network configurations interactively and potentially
  also injecting new events that were not present in the original trace.

  Currently InteractiveReplayer does not support live controllers, and instead
  mocks out controllers to prevent non-determinism and timeout issues.
  '''
  supported_input_events = set([SwitchFailure, SwitchRecovery, LinkFailure,
                                LinkRecovery, HostMigration, TrafficInjection])
  supported_internal_events = set([ControlMessageReceive])

  def __init__(self, simulation_cfg, superlog_path_or_dag, mock_controllers=True, input_logger=None):
    # TODO(cs): allow user to specify a round number where they want to stop,
    # otherwise play forward events without asking for interactive ack.
    Interactive.__init__(self, simulation_cfg, input_logger=input_logger)

    if mock_controllers is False:
      raise NotImplementedError("Live controllers not yet supported")
    self.mock_controllers = mock_controllers

    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents.
      self.event_list = EventDag(log_parser.parse_path(superlog_path)).events
    else:
      self.event_list = superlog_path_or_dag.events

    # TODO(cs): support compute_interpolated_time whenever we support
    # non-mocked controllers.

    if self.mock_controllers:
      self.event_list = [ e for e in self.event_list
                          if type(e) in InteractiveReplayer.supported_input_events or
                             type(e) in InteractiveReplayer.supported_internal_events ]


  def simulate(self, bound_objects=()):
    # TODO(cs): add interactive prompt commands for examining next pending
    # event, inject next pending event, examining total pending events
    # remaining.
    if self.mock_controllers:
      Interactive.simulate(self, boot_controllers=boot_mock_controllers,
                           connect_to_controllers=connect_to_mock_controllers,
                           bound_objects=bound_objects)
    else: # not self.mock_controllers
      Interactive.simulate(self, simulation=simulation, bound_objects=bound_objects)

  def default_command(self):
    return "next"

  def next_step(self):
    time.sleep(0.05)
    self.logical_time += 1
    self._forwarded_this_step = 0

    if len(self.event_list) == 0:
      msg.fail("No more events to inject")
    else:
      next_event = self.event_list.pop(0)
      msg.success("Injecting %r" % next_event)
      if type(next_event) in InteractiveReplayer.supported_input_events:
        next_event.proceed(self.simulation)
      else: # type(next_event) in InteractiveReplayer.supported_internal_events
        next_event.manually_inject(self.simulation)

    print "-------------------"
    print "Advanced to step %d" % self.logical_time
