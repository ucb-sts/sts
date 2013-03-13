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

import os
import time
import logging
from sts.replay_event import WaitTime
from sts.syncproto.base import SyncTime
from sts.util.convenience import timestamp_string
import sts.dataplane_traces.trace_generator as tg

# TODO(cs): need to copy some optional params from Fuzzer ctor to Replayer
# ctor
replay_config_template = '''
from config.experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import Replayer
from sts.simulation_state import SimulationConfig

simulation_config = %s

control_flow = Replayer(simulation_config, "%s",
                        wait_on_deterministic_values=%s)
# Invariant check: %s
'''

mcs_config_template = '''
from config.experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import EfficientMCSFinder
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

simulation_config = %s

control_flow = EfficientMCSFinder(simulation_config, "%s",
                                  wait_on_deterministic_values=%s,
                                  invariant_check_name=%s)
'''

log = logging.getLogger("input_logger")

class InputLogger(object):
  '''Log input events injected by a control_flow.Fuzzer'''

  def __init__(self, output_path=None):
    '''
    Automatically generate an output_path in input_traces/
    if one is not provided.
    '''
    self.output_path = output_path
    self.dp_events = []
    self.last_time = SyncTime.now()
    self._disallow_timeouts = False
    self._events_after_close = []
    self.output = None

  def open(self, results_dir=None):
    if results_dir != None:
      self.output_path = results_dir + "/events.trace"
      self.dp_trace_path = results_dir + "/dataplane.trace"
      self.replay_cfg_path = results_dir + "/replay_config.py"
      self.mcs_cfg_path = results_dir + "/mcs_config.py"
    else:
      if self.output_path is None:
        now = timestamp_string()
        self.output_path = "input_traces/" + now + ".trace"
      basename = os.path.basename(self.output_path)

      self.dp_trace_path = "./dataplane_traces/" + basename
      self.replay_cfg_path = "./config/" + basename.replace(".trace", ".py")
      self.mcs_cfg_path = "./config/" + basename.replace(".trace", "") + "_mcs.py"

    self.output = open(self.output_path, 'w')

  def disallow_timeouts(self):
    self._disallow_timeouts = True

  def allow_timeouts(self):
    self._disallow_timeouts = False

  def _serialize_event(self, event, output):
    if self._disallow_timeouts and hasattr(event, "disallow_timeouts"):
      event.timeout_disallowed = True
    self.last_time = event.time
    json_hash = event.to_json()
    log.debug("logging event %r" % event)
    output.write(json_hash + '\n')

  def log_input_event(self, event, dp_event=None):
    '''
    Log the event as a json hash. Note that we log dataplane events in a
    separate pickle log, so we optionally allow a packet parameter to be
    logged separately.
    '''
    if not self.output:
      raise Exception("Not opened -- call InputLogger.open")
    if not self.output.closed:
      self._serialize_event(event, self.output)
      if dp_event is not None:
        self.dp_events.append(dp_event)
    else:
      self._events_after_close.append(event)

  def dump_buffered_events(self, events):
    ''' If there were un-acknowledge message receives or state changes at the
    end of the run, dump them to a separate input trace ".unacked" '''
    with open(self.output_path + ".unacked", 'w') as output:
      for event in events + self._events_after_close:
        self._serialize_event(event, output)

  def close(self, control_flow, simulation_cfg, skip_mcs_cfg=False):
    # First, insert a WaitTime, in case there was a controller crash
    self.log_input_event(WaitTime(1.0, time=self.last_time))
    # Flush the json input log
    self.output.close()

    # Grab the dataplane trace path (might be pre-defined, or Fuzzed)
    if self.dp_events != []:
      # If the Fuzzer was injecting random traffic, write the dataplane trace
      tg.write_trace_log(self.dp_events, self.dp_trace_path)
      simulation_cfg.dataplane_trace_path = self.dp_trace_path

    # Write the config files
    path_templates = [(self.replay_cfg_path, replay_config_template)]
    if not skip_mcs_cfg:
      path_templates.append((self.mcs_cfg_path, mcs_config_template))

    wait_on_deterministic_values = False
    if hasattr(control_flow.sync_callback, "record_deterministic_values"):
      wait_on_deterministic_values = control_flow.sync_callback.record_deterministic_values

    for path, template in path_templates:
      with open(path, 'w') as cfg_out:
        config_string = template % (str(simulation_cfg),
                                    self.output_path,
                                    str(wait_on_deterministic_values),
                                    "'%s'" % str(control_flow.invariant_check_name))
        cfg_out.write(config_string)
