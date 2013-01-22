from experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.control_flow import Fuzzer, Interactive
from sts.input_traces.input_logger import InputLogger
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig

# Use POX as our controller
command_line = ('''./pox.py --verbose --random-seed=1 '''
                #'''sts.syncproto.pox_syncer --blocking=False '''
                #'''openflow.mock_discovery forwarding.l2_multi '''
                '''openflow.discovery forwarding.l2_multi '''
                #'''sts.util.socket_mux.pox_monkeypatcher '''
                '''openflow.of_01 --address=__address__ --port=__port__''')
controllers = [ControllerConfig(command_line, cwd="betta",
  #sync="tcp:localhost:18899"
  )
  ]
topology_class = MeshTopology
topology_params = "num_switches=2"
dataplane_trace = "dataplane_traces/ping_pong_same_subnet.trace"

simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params,
                                     dataplane_trace=dataplane_trace,
                                     #multiplex_sockets=True
                                     )

def my_funky_invariant_check(simulation):
  from sts.invariant_checker import InvariantChecker
  result = InvariantChecker.check_loops(simulation)
  if result:
    return result
  result = InvariantChecker.check_connectivity(simulation)
  if not result:
    print "Connectivity established - bailing out"
    import sys
    sys.exit(0)
  return []



control_flow = Fuzzer(simulation_config, check_interval=20,
                      #mock_link_discovery=True,
                      halt_on_violation=True,
                      input_logger=InputLogger(),
                      invariant_check=my_funky_invariant_check,
                      steps=141,
                      #random_seed=466448715
                      )
#control_flow = Interactive(simulation_config, input_logger=InputLogger())
