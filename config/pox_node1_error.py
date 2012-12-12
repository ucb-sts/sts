
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import Replayer
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig
from sts.control_flow.event_scheduler import DumbEventScheduler

simulation_config = SimulationConfig(controller_configs=[ControllerConfig(cmdline='./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi messenger.messenger samples.nommessenger', address='127.0.0.1', port=8888, cwd='pox', sync='tcp:localhost:18899')],
                                     topology_class=FatTree,
                                     topology_params="",
                                     patch_panel_class=BufferedPatchPanel,
                                     dataplane_trace="dataplane_traces/ping_pong_fat_tree.trace",
                                     switch_init_sleep_seconds=False)

def create_scheduler(simulation):
    return DumbEventScheduler(simulation,
                              timeout_seconds=0.0)

control_flow = Replayer(simulation_config,
                       "input_traces/pox_node1_error.trace",
                       create_event_scheduler=create_scheduler)
