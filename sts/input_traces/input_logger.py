# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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

import os
import time
import logging
from sts.replay_event import WaitTime
from sts.syncproto.base import SyncTime
from sts.util.convenience import timestamp_string
import sts.dataplane_traces.trace_generator as tg

# N.B. invoking replay_config.py should not overwrite the original
# events.trace, since experiments/setup.py automatically creates a new
# experiments subdirectory based on the name of the config file.

# TODO(cs): need to copy some optional params from Fuzzer ctor to Replayer
# ctor
replay_config_template = '''
from config.experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow.replayer import Replayer
from sts.simulation_state import SimulationConfig
from sts.input_traces.input_logger import InputLogger

simulation_config = %s

control_flow = Replayer(simulation_config, "%s",
                        input_logger=InputLogger(),
                        wait_on_deterministic_values=%s,
                        allow_unexpected_messages=False,
                        delay_flow_mods=%s,
                        default_dp_permit=False,
                        pass_through_whitelisted_messages=False,
                        invariant_check_name=%s,
                        bug_signature=%s)
'''

# TODO(cs): add input_logger to interactive_replayer in case they want to
# perturb the inputs?
interactive_replay_config_template = '''
from config.experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow.interactive_replayer import InteractiveReplayer
from sts.simulation_state import SimulationConfig
from sts.input_traces.input_logger import InputLogger

simulation_config = %s

control_flow = InteractiveReplayer(simulation_config, "%s")
# wait_on_deterministic_values=%s
# delay_flow_mods=%s
# Invariant check: %s
# Bug signature: %s
'''

openflow_replay_config_template = '''
from config.experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow.openflow_replayer import OpenFlowReplayer
from sts.simulation_state import SimulationConfig
from sts.input_traces.input_logger import InputLogger

simulation_config = %s

control_flow = OpenFlowReplayer(simulation_config, "%s")
# wait_on_deterministic_values=%s
# delay_flow_mods=%s
# Invariant check: %s
# Bug signature: %s
'''

mcs_config_template = '''
from config.experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow.mcs_finder import EfficientMCSFinder
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

simulation_config = %s

control_flow = EfficientMCSFinder(simulation_config, "%s",
                                  wait_on_deterministic_values=%s,
                                  default_dp_permit=False,
                                  pass_through_whitelisted_messages=False,
                                  delay_flow_mods=%s,
                                  invariant_check_name=%s,
                                  bug_signature=%s)
'''

log = logging.getLogger("input_logger")

class InputLogger(object):
  '''Log input events injected by a control_flow.Fuzzer'''

  def __init__(self):
    self.last_time = SyncTime.now()
    self._disallow_timeouts = False
    self._events_after_close = []
    self.output = None
    self.output_path = ""

  def open(self, results_dir=None, output_filename="events.trace"):
    if results_dir is not None:
      self.output_path = results_dir + "/" + output_filename
      self.replay_cfg_path = results_dir + "/replay_config.py"
      self.mcs_cfg_path = results_dir + "/mcs_config.py"
      self.interactive_replay_cfg_path = results_dir + "/interactive_replay_config.py"
      self.openflow_replay_cfg_path = results_dir + "/openflow_replay_config.py"
    else:
      raise ValueError("Default results_dir currently not supported")
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

  def log_input_event(self, event):
    '''
    Log the event as a json hash.
    '''
    if not self.output:
      raise Exception("Not opened -- call InputLogger.open")
    if not self.output.closed:
      self._serialize_event(event, self.output)
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

    # Write the config files
    path_templates = [(self.replay_cfg_path, replay_config_template),
                      (self.interactive_replay_cfg_path, interactive_replay_config_template),
                      (self.openflow_replay_cfg_path, openflow_replay_config_template)]
    if not skip_mcs_cfg:
      path_templates.append((self.mcs_cfg_path, mcs_config_template))

    wait_on_deterministic_values = False
    if hasattr(control_flow.sync_callback, "record_deterministic_values"):
      wait_on_deterministic_values = control_flow.sync_callback.record_deterministic_values

    delay_flow_mods = False
    if hasattr(control_flow, "delay_flow_mods"):
      delay_flow_mods = control_flow.delay_flow_mods

    bug_signature = ""
    if hasattr(control_flow, "bug_signature"):
      bug_signature = control_flow.bug_signature

    for path, template in path_templates:
      with open(path, 'w') as cfg_out:
        config_string = template % (str(simulation_cfg),
                                    self.output_path,
                                    str(wait_on_deterministic_values),
                                    str(delay_flow_mods),
                                    "'%s'" % str(control_flow.invariant_check_name),
                                    '"%s"' % str(bug_signature))
        cfg_out.write(config_string)
