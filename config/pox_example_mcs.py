
from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import MCSFinder, Peeker
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

controllers = [ControllerConfig(cmdline='./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi',
                                address='127.0.0.1', port=8888, cwd='pox', sync='tcp:localhost:18899')]
topology_class = MeshTopology
topology_params = "num_switches=2"
dataplane_trace = "dataplane_traces/pox_example_replay.trace"
simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     dataplane_trace=dataplane_trace)

control_flow = MCSFinder(simulation_config, "input_traces/pox_example_replay.trace",
                         invariant_check_name="InvariantChecker.check_liveness",
                         mcs_trace_path="input_traces/pox_example_mcs.trace",
                         extra_log=open("mcs_log.txt", "w", 0),
                         dump_runtime_stats=True)
