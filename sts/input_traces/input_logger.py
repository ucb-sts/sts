import os
import time
import logging
from sts.replay_event import WaitTime
import sts.dataplane_traces.trace_generator as tg

# TODO(cs): need to copy some optional params from Fuzzer ctor to Replayer
# ctor
config_template = '''
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import Replayer

controllers = %s
topology_class = %s
topology_params = "%s"
patch_panel_class = %s
control_flow = Replayer("%s")
dataplane_trace = %s
'''

log = logging.getLogger("input_logger")

class InputLogger(object):
  '''Log input events injected by a control_flow.Fuzzer'''

  def __init__(self, output_path=None):
    '''
    Automatically generate an output_path in input_traces/
    if one is not provided.
    '''
    if output_path is None:
      now = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())
      output_path = "input_traces/" + now + ".trace"
    self.output_path = output_path
    self.output = open(output_path, 'a')
    self.dp_events = []
    basename = os.path.basename(output_path)
    self.dp_trace_path = "./dataplane_traces/" + basename
    self.cfg_path = "./config/" + basename.replace(".trace", ".py")

  def log_input_event(self, event, dp_event=None):
    '''
    Log the event as a json hash. Note that we log dataplane events in a
    separate pickle log, so we optionally allow a packet parameter to be
    logged separately.
    '''
    json_hash = event.to_json()
    log.debug("logging event %s" % event)
    self.output.write(json_hash + '\n')
    if dp_event is not None:
      self.dp_events.append(dp_event)

  def close(self, simulation):
    # First, insert a WaitTime, in case there was a controller crash
    self.log_input_event(WaitTime(1.0))
    # Flush the json input log
    self.output.close()

    # Grab the dataplane trace path (might be pre-defined, or Fuzzed)
    if simulation._dataplane_trace_path is not None:
      self.dp_trace_path = "\"" + simulation._dataplane_trace_path + "\""
    elif self.dp_events != []:
      # If the Fuzzer was injecting random traffic, write the dataplane trace
      tg.write_trace_log(self.dp_events, self.dp_trace_path)
      self.dp_trace_path = "\"" + self.dp_trace_path + "\""
    else:
      self.dp_trace_path = None

    # Write the config file
    with open(self.cfg_path, 'w') as cfg_out:
      config_string = config_template % (str(simulation.controller_configs),
                                         simulation._topology_class.__name__,
                                         simulation._topology_params,
                                         simulation._patch_panel_class.__name__,
                                         self.output_path,
                                         self.dp_trace_path)
      cfg_out.write(config_string)
