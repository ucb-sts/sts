from config.experiment_config_lib import ControllerConfig
from sts.control_flow import Fuzzer
from sts.input_traces.input_logger import InputLogger
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

# Use NOX as our controller
command_line = "./nox_core -i ptcp:6633 routing"
controllers = [ControllerConfig(command_line, cwd="nox_classic/build/src", address="127.0.0.1", port=6633)]

dataplane_trace = "dataplane_traces/ping_pong_fat_tree.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     dataplane_trace=dataplane_trace)

# Use a Fuzzer (already the default)
control_flow = Fuzzer(simulation_config, input_logger=InputLogger(),
                      check_interval=80,
                      invariant_check=InvariantChecker.check_connectivity)

