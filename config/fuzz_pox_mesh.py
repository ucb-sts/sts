from experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import Fuzzer
from sts.input_traces.input_logger import InputLogger
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

# Use POX as our controller
command_line = ('''./pox.py --verbose --no-cli sts.syncproto.pox_syncer '''
                '''samples.topo forwarding.l2_multi '''
                '''sts.util.socket_mux.pox_monkeypatcher '''
                '''openflow.of_01 --address=../sts_socket_pipe''')
controllers = [ControllerConfig(command_line, address="sts_socket_pipe", cwd="pox", sync="tcp:localhost:18899")]

topology_class = MeshTopology
topology_params = "num_switches=2"
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     dataplane_trace=dataplane_trace,
                                     monkey_patch_select=True)

control_flow = Fuzzer(simulation_config, check_interval=1, halt_on_violation=True,
                      input_logger=InputLogger(),
                      invariant_check=InvariantChecker.check_liveness)
