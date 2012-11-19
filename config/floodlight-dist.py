from experiment_config_lib import ControllerConfig
from sts.topology import FatTree, MeshTopology, BufferedPatchPanel
from sts.control_flow import Fuzzer,Interactive
from sts.input_traces.input_logger import InputLogger
from sts.invariant_checker import InvariantChecker

# Use POX as our controller
command_line_server = "./fl-server.sh"
command_line_client = "./fl-client.sh"
controllers = [
    ControllerConfig(command_line_server, cwd="../floodlight-w3", address="127.0.0.1", port=6633),
    ControllerConfig(command_line_client, cwd="../floodlight-w3", address="127.0.0.1", port=6634)
]

# Use a FatTree with 4 pods (already the default)
# (specify the class, but don't instantiate the object)
topology_class = MeshTopology

topology_params = "num_switches=2"

# Use a BufferedPatchPanel (already the default)
# (specify the class, but don't instantiate the object)
patch_panel_class = BufferedPatchPanel

from sts.util.convenience import timestamp_string

# Use a Fuzzer (already the default)
control_flow = Interactive(input_logger=InputLogger(output_path="input_traces/fl_"+timestamp_string()+".trace"), switch_init_sleep_seconds=0) #Fuzzer(input_logger=InputLogger(),
                           #check_interval=80,
                           #invariant_check=InvariantChecker.check_connectivity)

# Specify None as the dataplane trace (already the default)
# Otherwise, specify the path to the trace file
# (e.g. "dataplane_traces/ping_pong_same_subnet.trace")
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"
