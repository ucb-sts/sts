from experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import Fuzzer, Interactive
from sts.input_traces.input_logger import InputLogger
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

# Use POX as our controller
command_line = ('''./pox.py --verbose openflow.debug ''' #sts.syncproto.pox_syncer '''
                '''forwarding.l2_multi '''
                #'''sts.util.socket_mux.pox_monkeypatcher '''
                '''openflow.of_01 --address=__address__ --port=__port__''')
controllers = [ControllerConfig(command_line, cwd="betta")]

topology_class = MeshTopology
topology_params = "num_switches=2"
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     dataplane_trace=dataplane_trace,
                                     multiplex_sockets=False)

control_flow = Fuzzer(simulation_config, check_interval=80,
                      halt_on_violation=False,
                      input_logger=InputLogger(),
                      invariant_check=InvariantChecker.check_connectivity)
#control_flow = Interactive(simulation_config, input_logger=InputLogger())
