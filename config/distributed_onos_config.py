
import os
from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import Fuzzer, Interactive
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig

if 'CLUSTER' not in os.environ:
  raise RuntimeError('''Need to set $CLUSTER. See '''
                     '''https://wiki.onlab.us:8443/display/Eng/ONOS+Development+VM.\n'''
                     '''On c5:\n'''
                     '''export CLUSTER=${HOME}/.cluster.hosts\n'''
                     '''export ONOS_CLUSTER_BASENAME="onosdev"\n'''
                     '''export ONOS_CLUSTER_NR_NODES=2\n'''
                     '''export PATH=${HOME}/vagrant_onosdev/ONOS/cluster-mgmt/bin:$PATH''')

def get_additional_metadata():
  path = "/home/rcs/vagrant_onosdev"
  return {
    'commit' : backtick("git rev-parse HEAD", cwd=path),
    'branch' : backtick("git rev-parse --abbrev-ref HEAD", cwd=path)
  }

# Use ONOS as our controller.
# TODO(cs): first make sure to clean up any preexisting ONOS instances.
# N.B. this command is for the entire cluster, not individual nodes.
start_cmd = (''' vagrant halt onosdev1 onosdev2; vagrant up onosdev1 onosdev2 ; '''
             ''' ./scripts/conf_setup.sh 2 ; zk start ; cassandra start; '''
             ''' onos start ; sleep 30 ''')
# N.B kills a single node.
kill_cmd = (''' vagrant ssh %s -c "cd ONOS; ./start-onos.sh stop"''')
# N.B. starts a single node.
restart_cmd = 'vagrant ssh %s -c "cd ONOS; ./start-onos.sh start"'
dummy_cmd = 'sleep 1'

controllers = [ControllerConfig(start_cmd, address="192.168.56.11", port=6633,
                                kill_cmd=kill_cmd % "onosdev1",
                                restart_cmd=restart_cmd % "onosdev1",
                                controller_type="onos",
                                cwd="/home/rcs/vagrant_onosdev"),
               ControllerConfig(dummy_cmd, address="192.168.56.12", port=6633,
                                kill_cmd=kill_cmd % "onosdev2",
                                restart_cmd=restart_cmd % "onosdev2",
                                controller_type="onos",
                                cwd="/home/rcs/vagrant_onosdev")]
topology_class = MeshTopology
topology_params = "num_switches=2"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     kill_controllers_on_exit=False)

#control_flow = Fuzzer(simulation_config, check_interval=20,
#                      halt_on_violation=True,
#                      input_logger=InputLogger(),
#                      invariant_check_name="InvariantChecker.check_loops")
control_flow = Interactive(simulation_config, input_logger=InputLogger())
