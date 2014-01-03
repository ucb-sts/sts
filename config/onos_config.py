
from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import Fuzzer
from sts.input_traces.input_logger import InputLogger
from sts.simulation_state import SimulationConfig
from sts.util.convenience import backtick

def get_additional_metadata():
  path = "/home/rcs/vagrant_onosdev"
  return {
    'commit' : backtick("git rev-parse HEAD", cwd=path),
    'branch' : backtick("git rev-parse --abbrev-ref HEAD", cwd=path)
  }

# Use ONOS as our controller.
# N.B. ./scripts/conf_setup.sh automatically clears the cassandra image. If
# you're running on a machine other than c5, you may have to modify
# conf_setup.sh to remove the interactive prompt for clearing the cassandra
# image.
start_cmd = ('''vagrant halt onosdev1; vagrant up onosdev1 ; ./scripts/conf_setup.sh 1 ;  '''
             ''' vagrant ssh onosdev1 -c "cd ONOS; ./start-zk.sh start; sleep 5; '''
             ''' ./start-cassandra.sh start; sleep 10; '''
             ''' ./start-onos.sh start; sleep 15"''')
restart_cmd = 'vagrant ssh onosdev1 -c "cd ONOS; ./start-onos.sh start"'
kill_cmd = 'vagrant ssh onosdev1 -c "cd ONOS; ./start-onos.sh stop"'

controllers = [ControllerConfig(start_cmd, address="192.168.56.11", port=6633,
                                restart_cmd=restart_cmd, kill_cmd=kill_cmd,
                                controller_type="onos",
                                cwd="/home/rcs/vagrant_onosdev")]
topology_class = MeshTopology
topology_params = "num_switches=2"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     kill_controllers_on_exit=False)

control_flow = Fuzzer(simulation_config, check_interval=20,
                      halt_on_violation=True,
                      input_logger=InputLogger(),
                      invariant_check_name="InvariantChecker.check_loops")

