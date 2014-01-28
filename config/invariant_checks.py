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

def check_for_flow_entry(simulation):
  # Temporary hack for "Overlapping flow entries" bug.
  for sw in simulation.topology.switches:
    for entry in sw.table.entries:
      if entry.priority == 123:
        return ["123Found"]
  return []

class TimeOutOnConnectivity(object):
  ''' If connectivity hasn't been established in X invocations of this
  check, return a violation.
  '''
  def __init__(self, max_invocations=40):
    self.max_invocations = max_invocations
    self.invocations_since_connectivity = 0

  def __call__(self, simulation):
    unconnected = InvariantChecker.check_connectivity
    if unconnected == []:
      self.invocations_since_connectivity = 0
      return []
    else:
      self.invocations_since_connectivity += 1
      if self.invocations_since_connectivity >= self.max_invocations:
        return [unconnected]
      return []

# Note: make sure to add new custom invariant checks to this dictionary!
name_to_invariant_check = {
  "check_everything" : check_everything,
  "bail_on_connectivity" : bail_on_connectivity,
  "check_for_loops_or_connectivity" : check_for_loops_or_connectivity,
  "check_for_loops_blackholes_or_connectivity" : check_for_loops_blackholes_or_connectivity,
  "check_for_loops_blackholes" : check_for_loops_blackholes,
  "check_for_invalid_ports" : check_for_invalid_ports,
  "check_for_flow_entry" : check_for_flow_entry,
  "time_out_on_connectivity" : TimeOutOnConnectivity(),
  "InvariantChecker.check_liveness" : InvariantChecker.check_liveness,
  "InvariantChecker.check_loops" : InvariantChecker.check_loops,
  "InvariantChecker.python_check_loops" : InvariantChecker.python_check_loops,
  "InvariantChecker.python_check_connectivity" : InvariantChecker.python_check_connectivity,
  "InvariantChecker.python_check_persistent_connectivity" : InvariantChecker.python_check_persistent_connectivity,
  "InvariantChecker.check_connectivity" : InvariantChecker.check_connectivity,
  "InvariantChecker.check_persistent_connectivity" : InvariantChecker.check_persistent_connectivity,
  "InvariantChecker.check_blackholes" : InvariantChecker.python_check_blackholes,
  "InvariantChecker.check_correspondence" : InvariantChecker.check_correspondence,
}

# Now make sure that we always check if all controllers are down (should never
# happen) before checking any other invariant
name_to_invariant_check = { k: ComposeChecks(InvariantChecker.all_controllers_dead, v) for k,v in name_to_invariant_check.items() }
