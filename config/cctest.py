from experiment_config_lib import ControllerConfig
from sts.control_flow import Fuzzer
from sts.simulation_state import SimulationConfig

# Use POX as our controller
#command_line = "./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_learning messenger.messenger samples.nommessenger"
command_line = "./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi messenger.messenger samples.nommessenger"
controllers = [ControllerConfig(command_line, cwd="pox", sync="tcp:localhost:18899")]

dataplane_trace = "dataplane_traces/ping_pong_fat_tree.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     dataplane_trace=dataplane_trace)

control_flow = Fuzzer(simulation_config, check_interval=1)
