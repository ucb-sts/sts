from sts.invariant_checker import InvariantChecker
import sys

def check_everything(simulation):
  # Check liveness once at the beginning
  # If there are no more live controllers, stop
  violations = []
  down_controllers = InvariantChecker.check_liveness(simulation)
  violations = down_controllers
  # Check other invariants without checking liveness
  checks = [ InvariantChecker.check_loops,
             InvariantChecker.python_check_blackholes,
             InvariantChecker.check_connectivity ]
  for check in checks:
    violations += check(simulation, check_liveness_first=False)
  violations = list(set(violations))
  return violations

def bail_on_connectivity(simulation):
  result = InvariantChecker.check_connectivity(simulation)
  if not result:
    print "Connectivity established - bailing out"
    sys.exit(0)
  return []

def check_for_loops_or_connectivity(simulation):
  result = InvariantChecker.check_loops(simulation)
  if result:
    return result
  return bail_on_connectivity(simulation)

def check_for_loops_blackholes_or_connectivity(simulation):
  for check in [InvariantChecker.check_loops, InvariantChecker.python_check_blackholes]:
    result = check(simulation)
    if result:
      return result
  return bail_on_connectivity(simulation)

def check_for_loops_blackholes(simulation):
  for check in [InvariantChecker.check_loops, InvariantChecker.python_check_blackholes]:
    result = check(simulation)
    if result:
      return result
  return []

# Note: make sure to add new custom invariant checks to this dictionary!
name_to_invariant_check = {
  "check_everything" : check_everything,
  "check_for_loops_or_connectivity" : check_for_loops_or_connectivity,
  "check_for_loops_blackholes_or_connectivity" : check_for_loops_blackholes_or_connectivity,
  "check_for_loops_blackholes" : check_for_loops_blackholes,
  "InvariantChecker.check_liveness" :  InvariantChecker.check_liveness,
  "InvariantChecker.check_loops" :  InvariantChecker.check_loops,
  "InvariantChecker.python_check_loops" :  InvariantChecker.python_check_loops,
  "InvariantChecker.python_check_connectivity" :  InvariantChecker.python_check_connectivity,
  "InvariantChecker.check_connectivity" :  InvariantChecker.check_connectivity,
  "InvariantChecker.check_blackholes" :  InvariantChecker.python_check_blackholes,
  "InvariantChecker.check_correspondence" :  InvariantChecker.check_correspondence,
}
