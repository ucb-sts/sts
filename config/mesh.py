from experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology, BufferedPatchPanel
from sts.control_flow import Interactive
from input_traces.input_logger import InputLogger

# Use POX as our controller
command_line = "./pox/pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__"
controllers = [ControllerConfig(command_line)]

# Use a FatTree with 4 pods (already the default)
# (specify the class, but don't instantiate the object)
topology_class = MeshTopology
# Comma-delimited list of arguments to pass into the FatTree constructor,
# specified just as you would type them within the parens.
topology_params = "num_switches=2"

# Use a BufferedPatchPanel (already the default)
# (specify the class, but don't instantiate the object)
patch_panel_class = BufferedPatchPanel

# Use a Fuzzer (already the default)
control_flow = Interactive()

# Specify None as the dataplane trace (already the default)
# Otherwise, specify the path to the trace file
# (e.g. "dataplane_traces/ping_pong_same_subnet.trace")
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"
