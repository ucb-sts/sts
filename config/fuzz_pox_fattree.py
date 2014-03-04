from config.experiment_config_lib import ControllerConfig
from sts.control_flow.fuzzer import Fuzzer
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig
from sts.invariant_checker import InvariantChecker

# Use POX as our controller
start_cmd = ('''./pox.py --verbose --no-cli sts.syncproto.pox_syncer --blocking=False '''
                '''samples.topo forwarding.l2_multi '''
                '''sts.util.socket_mux.pox_monkeypatcher '''
                '''openflow.of_01 --address=../sts_socket_pipe''')
controllers = [ControllerConfig(start_cmd, address="sts_socket_pipe", cwd="pox", sync="tcp:localhost:18899")]

dataplane_trace = "dataplane_traces/ping_pong_fat_tree.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     dataplane_trace=dataplane_trace,
                                     multiplex_sockets=True)

# Use a Fuzzer (already the default)
control_flow = Fuzzer(simulation_config, check_interval=1, halt_on_violation=True,
                      input_logger=InputLogger(),
                      invariant_check_name="InvariantChecker.check_liveness")

