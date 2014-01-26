
from config.experiment_config_lib import ControllerConfig
from sts.topology import FatTree, MeshTopology
from sts.control_flow import Fuzzer, Interactive
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig
from sts.util.convenience import backtick

def get_additional_metadata():
  path = "dart_pox"
  return {
    'commit' : backtick("git rev-parse HEAD", cwd=path),
    'branch' : backtick("git rev-parse --abbrev-ref HEAD", cwd=path),
    'remote' : backtick("git remote show origin", cwd=path),
  }


# Use POX as our controller
start_cmd = ('''./pox.py --verbose --unthreaded-sh '''
             '''sts.util.socket_mux.pox_monkeypatcher  '''
             # --snapshot_address=/Users/cs/Research/UCB/code/sts/snapshot_socket'''
             #'''sts.syncproto.pox_syncer --blocking=False '''
             '''openflow.discovery forwarding.topo_proactive '''
             '''openflow.of_01 --address=__address__ --port=__port__''')

controllers = [ControllerConfig(start_cmd, cwd="dart_pox")]
topology_class = MeshTopology
topology_params = "num_switches=3"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     multiplex_sockets=True,
                                     topology_params=topology_params)

control_flow = Interactive(simulation_config,
                      input_logger=InputLogger())
