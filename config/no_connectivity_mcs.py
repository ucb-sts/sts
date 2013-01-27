
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import MCSFinder
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

simulation_config = SimulationConfig(controller_configs=[ControllerConfig(cmdline='./pox.py --verbose sts.syncproto.pox_syncer --blocking=False openflow.discovery forwarding.l2_multi sts.util.socket_mux.pox_monkeypatcher openflow.of_01 --address=__address__ --port=__port__', address='127.0.0.1', port=6633, cwd='pox')],
                 topology_class=MeshTopology,
                 topology_params="num_switches=2",
                 patch_panel_class=BufferedPatchPanel,
                 dataplane_trace="dataplane_traces/ping_pong_same_subnet.trace",
                 multiplex_sockets=True)

control_flow = MCSFinder(simulation_config, "input_traces/2013_01_21_21_50_32.trace",
                         invariant_check=InvariantChecker.check_liveness,
                         mcs_trace_path="input_traces/2013_01_21_21_50_32_mcs_final.trace",
                         wait_on_deterministic_values=False)
