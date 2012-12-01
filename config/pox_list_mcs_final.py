
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import Replayer

controllers = [ControllerConfig(cmdline='./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi messenger.messenger samples.nommessenger', address='127.0.0.1', port=8888, cwd='pox', sync='tcp:localhost:18899')]
topology_class = MeshTopology
topology_params = "num_switches=2"
patch_panel_class = BufferedPatchPanel
control_flow = Replayer("input_traces/pox_list_mcs_final.trace",
                        wait_time=0.2, max_rounds=5,
                        switch_init_sleep_seconds=2.0)
# MCS trace path: input_traces/pox_list_mcs_final_mcs_final.trace
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"
