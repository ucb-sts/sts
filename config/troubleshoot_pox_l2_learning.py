
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import Replayer

controllers = [ControllerConfig(cmdline='./pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__ samples.topo forwarding.l2_learning', address='127.0.0.1', port=8888, cwd='pox')]
topology_class = MeshTopology
topology_params = "num_switches=2"
patch_panel_class = BufferedPatchPanel
control_flow = Replayer("input_traces/troubleshoot_pox_l2_learning.trace")
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"
