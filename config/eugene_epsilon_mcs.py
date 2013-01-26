
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import EfficientMCSFinder
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

simulation_config = SimulationConfig(controller_configs=[ControllerConfig(cmdline='./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi messenger.messenger samples.nommessenger', address='127.0.0.1', port=6633, cwd='pox', sync='tcp:localhost:18899')],
                 topology_class=MeshTopology,
                 topology_params="num_switches=4",
                 dataplane_trace="dataplane_traces/ping_pong_same_subnet_4_switches.trace")

control_flow = EfficientMCSFinder(simulation_config, "input_traces/eugene_epsilon.trace",
                                  invariant_check=InvariantChecker.check_liveness,
                                  mcs_trace_path="input_traces/eugene_epsilon_mcs_final.trace",
                                  extra_log=open("mcs_log.out", "w"),
                                  epsilon_seconds=0.25)
