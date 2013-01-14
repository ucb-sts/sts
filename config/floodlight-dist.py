from experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import Interactive
from sts.invariant_checker import InvariantChecker
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig

# Use POX as our controller
command_line_server = "./fl-server.sh"
command_line_client = "./fl-client.sh"
controllers = [
    ControllerConfig(command_line_server, cwd="../floodlight-w3", address="127.0.0.1", port=6633, sync="tcp:127.0.0.1:19999"),
    ControllerConfig(command_line_client, cwd="../floodlight-w3", address="127.0.0.1", port=6634, sync="tcp:127.0.0.1:20000")
]

topology_class = MeshTopology
topology_params = "num_switches=2"
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     dataplane_trace=dataplane_trace)

from sts.util.convenience import timestamp_string

# Use a Fuzzer (already the default)
control_flow = Interactive(simulation_config, input_logger=InputLogger(output_path="input_traces/fl_"+timestamp_string()+".trace")) #Fuzzer(input_logger=InputLogger(),
                           #check_interval=80,
                           #invariant_check=InvariantChecker.check_connectivity)

