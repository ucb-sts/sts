
from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow.mcs_finder import EfficientMCSFinder
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig
from sts.control_flow.peeker import SnapshotPeeker

# Use POX as our controller
start_cmd = ('''./pox.py --verbose '''
             '''openflow.discovery forwarding.l2_multi '''
             '''sts.util.socket_mux.pox_monkeypatcher --snapshot_address=../snapshot_socket'''
             '''openflow.of_01 --address=__address__ --port=__port__''')

controllers = [ControllerConfig(start_cmd, cwd="pox", snapshot_address="./snapshot_socket")]
topology_class = MeshTopology
topology_params = "num_switches=2"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     multiplex_sockets=True)

peeker = SnapshotPeeker(simulation_config)
control_flow = EfficientMCSFinder(simulation_config, "/PATH/TO/EVENT.TRACE",
                                  wait_on_deterministic_values=False,
                                  delay_flow_mods=False,
                                  invariant_check_name="InvariantChecker.python_check_loops",
                                  transform_dag=peeker.peek)
