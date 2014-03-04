from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology, BufferedPatchPanel
from sts.control_flow.interactive import Interactive
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig

# Use POX as our controller
start_cmd = "./pox.py --verbose openflow.of_01 --address=__address__ --port=__port__ openflow.discovery forwarding.l2_multi"
controllers = [ControllerConfig(start_cmd, cwd="pox", address="127.0.0.1", port=8888)]
topology_class = MeshTopology
topology_params = "num_switches=4"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params)

control_flow = Interactive(simulation_config, input_logger=InputLogger())
