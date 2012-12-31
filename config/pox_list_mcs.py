
from experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import MCSFinder, Peeker
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

controllers = [ControllerConfig(cmdline='./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__ sts.syncproto.pox_syncer samples.topo forwarding.l2_multi messenger.messenger samples.nommessenger', address='127.0.0.1', port=8888, cwd='pox', sync='tcp:localhost:18899')]
topology_class = MeshTopology
topology_params = "num_switches=4"
dataplane_trace = "dataplane_traces/ping_pong_same_subnet_4_switches.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     switch_init_sleep_seconds=2.0,
                                     dataplane_trace=dataplane_trace)

peeker = Peeker(simulation_config)
control_flow = MCSFinder(simulation_config, "input_traces/pox_list_violation.trace",
                         #create_event_scheduler = lambda simulation: DumbEventScheduler(simulation),
                         #delay_input_events=True,
                         epsilon_seconds=0.5,
                         invariant_check=InvariantChecker.check_liveness,
                         mcs_trace_path="input_traces/pox_list_mcs_final.trace",
                         transform_dag=peeker.peek,
                         extra_log=open("mcs_log.txt", "w", 0),
                         dump_runtime_stats=True)
