from experiment_config_lib import ControllerConfig
from sts.topology import FatTree, BufferedPatchPanel
from sts.control_flow import Interactive
from sts.input_traces.input_logger import InputLogger

# Use POX as our controller
command_line = "./pox/pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__"
controllers = [ControllerConfig(command_line)]

# Use a FatTree with 3 pods
topology_class = FatTree
topology_params = "num_pods=2, gui=True"

# Use a BufferedPatchPanel (already the default)
patch_panel_class = BufferedPatchPanel

# Use Interactive
control_flow = Interactive(input_logger=InputLogger())

# Specify None as the dataplane trace (already the default)
dataplane_trace = None
