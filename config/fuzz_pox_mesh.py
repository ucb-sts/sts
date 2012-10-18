from experiment_config_lib import ControllerConfig
from sts.topology import FatTree, MeshTopology, BufferedPatchPanel
from sts.control_flow import Interactive, Fuzzer
from sts.input_traces.input_logger import InputLogger

# Use POX as our controller
command_line = "./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi messenger.messenger samples.nommessenger"
controllers = [ControllerConfig(command_line, cwd="pox", sync="tcp:localhost:18899")]

topology_class = MeshTopology
topology_params = "num_switches=2"
patch_panel_class = BufferedPatchPanel
control_flow = Fuzzer(check_interval=1, input_logger=InputLogger())
dataplane_trace = "dataplane_traces/ping_pong_fat_tree.trace"
