from sts.invariant_checker import InvariantChecker
import sys

class ComposeChecks(object):
  def __init__(self, check1, check2):
    self.check1 = check1
    self.check2 = check2

  def __call__(self, simulation):
    check1_results = self.check1(simulation)
    if check1_results != []:
      return check1_results
    return self.check2(simulation)

def check_everything(simulation):
  violations = []
  checks = [ InvariantChecker.check_liveness,
             InvariantChecker.check_loops,
             InvariantChecker.python_check_blackholes,
             InvariantChecker.check_connectivity,
             check_for_invalid_ports ]
  for check in checks:
    violations += check(simulation)
  violations = list(set(violations))
  return violations

def bail_on_connectivity(simulation):
  result = InvariantChecker.check_connectivity(simulation)
  if not result:
    print "Connectivity established - bailing out"
    sys.exit(0)
  return []

check_for_loops_or_connectivity = ComposeChecks(InvariantChecker.check_loops,
                                                bail_on_connectivity)

check_for_loops_blackholes_or_connectivity =\
  ComposeChecks(
    ComposeChecks(InvariantChecker.check_loops, InvariantChecker.python_check_blackholes),
    bail_on_connectivity)

check_for_loops_blackholes = ComposeChecks(InvariantChecker.check_loops,
                                           InvariantChecker.python_check_blackholes)

def check_for_invalid_ports(simulation):
  ''' Check if any of the switches have been asked to forward packets out
  ports that don't exist '''
  violations = []
  for sw in simulation.topology.switches:
    if sw.port_violations != []:
      violations += [ str(v) for v in sw.port_violations ]
  return violations

# Note: make sure to add new custom invariant checks to this dictionary!
name_to_invariant_check = {
  "check_everything" : check_everything,
  "check_for_loops_or_connectivity" : check_for_loops_or_connectivity,
  "check_for_loops_blackholes_or_connectivity" : check_for_loops_blackholes_or_connectivity,
  "check_for_loops_blackholes" : check_for_loops_blackholes,
  "check_for_invalid_ports" : check_for_invalid_ports,
  "InvariantChecker.check_liveness" :  InvariantChecker.check_liveness,
  "InvariantChecker.check_loops" :  InvariantChecker.check_loops,
  "InvariantChecker.python_check_loops" :  InvariantChecker.python_check_loops,
  "InvariantChecker.python_check_connectivity" :  InvariantChecker.python_check_connectivity,
  "InvariantChecker.check_connectivity" :  InvariantChecker.check_connectivity,
  "InvariantChecker.check_blackholes" :  InvariantChecker.python_check_blackholes,
  "InvariantChecker.check_correspondence" :  InvariantChecker.check_correspondence,
}

# Now make sure that we always check if all controllers are down (should never
# happen) before checking any other invariant
name_to_invariant_check = { k: ComposeChecks(InvariantChecker.all_controllers_dead, v) for k,v in name_to_invariant_check.items() }
