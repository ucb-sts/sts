'''
Three control flow types for running the simulation forward.
'''

import random

class ControlFlow(object):
  def __init__(self, topology, control_socket=None):
    self.topology = topology
    self.control_socket = control_socket
    self.invariant_checker = InvariantChecker(control_socket)

  def simulate(self):
    pass

class Replayer(ControlFlow):
  '''
  Replay events from a `superlog`, pruning as we go
  '''
  def __init__(self, topology, dag, control_socket=None):
    ControlFlow.__init__(topology, control_socket=control_socket)
    self.dag = dag

  def simulate(self):
    def increment_round():
      simulation.forward_data()
      # TODO(cs): more stuff to forward round?
    for pruned_event in dag.events():
      for event in dag.events(pruned_event):
        event.run(simulation)
        self.increment_round(simulation)

class InjectionBasedControlFlow(ControlFlow):
  def __init__(self, topology, control_socket=None, random_seed=0.0,
               dataplane_trace=None, steps=None):
    ControlFlow.__init__(topology, control_socket=control_socket)

    self.running = False

    # Logical time (round #) for the simulation execution
    self.logical_time = 0
    # How many logical rounds to execute before halting (None -> infinity) 
    self.steps = None

    # Make execution deterministic to allow the user to easily replay
    self.seed = random_seed
    self.random = random.Random(self.seed)
    self.traffic_generator = TrafficGenerator(self.random)

    # Format of trace file is a pickled array of DataplaneEvent objects
    self.dataplane_trace = None
    if dataplane_trace:
      self.dataplane_trace = pickle.load(file(dataplane_trace))

  def stop(self):
    self.running = False

class Fuzzer(InjectionBasedControlFlow):
  '''
  Inject random events. (Not the proper use of the word `Fuzzer`)
  '''
  def __init__(self, topology, fuzzer_params="configs/fuzzer_params.cfg",
               check_interval=35, trace_interval=10, random_seed=0.0, delay=0.1,
               dataplane_trace=None, control_socket=None):
    InjectionBasedControlFlow.__init__(topology, control_socket=control_socket,
                                       random_seed=random_seed,
                                       dataplane_trace=dataplane_trace)
    self.check_interval = check_interval
    self.trace_interval = trace_interval

    self.delay = delay

    self._load_fuzzer_params(fuzzer_params)

  def _load_fuzzer_params(self, fuzzer_params_path):
    if os.path.exists(fuzzer_params_path):
        self.params = __import__(fuzzer_params_path)
    else:
      # TODO: default values in case fuzzer_config is not present / missing directives
      raise IOError("Could not find logging config file: %s" % fuzzer_params)

  def simulate(self):
     self.loop()

  def loop(self):
    self.running = True
    if self.steps:
      end_time = self.logical_time + self.steps 
    else:
      end_time = sys.maxint
    while self.running and self.logical_time < end_time:
      self.logical_time += 1
      self.trigger_events()
      msg.event("Round %d completed." % self.logical_time)

      if (self.logical_time % self.check_interval) == 0:
        # Time to run correspondence!
        # spawn a thread for running correspondence. Make sure the controller doesn't 
        # think we've gone idle though: send OFP_ECHO_REQUESTS every few seconds
        # TODO: this is a HACK
        def do_correspondence():
          any_policy_violations = self.invariant_checker.check_correspondence(
                                    self.live_switches, self.live_links,
                                    self.topology.access_links)

          if any_policy_violations:
            msg.fail("There were policy-violations!")
          else:
            msg.interactive("No policy-violations!")
        thread = threading.Thread(target=do_correspondence)
        thread.start()
        while thread.isAlive():
          for switch in self.live_switches:
            # connection -> deferred io worker -> io worker
            switch.send(of.ofp_echo_request().pack())
          thread.join(2.0)
     
      if self.dataplane_trace and (self.logical_time % self.trace_interval) == 0:
        self.inject_trace_event()
        
      time.sleep(self.delay)


class Interactive(InjectionBasedControlFlow):
  '''
  Interactively inject inputs
  '''
  # TODO(cs): rather than just prompting "Continue to next round? [Yn]", allow
  #           the user to examine the state of the network interactively (i.e.,
  #           provide them with the normal POX cli + the simulated events
  def __init__(self, topology, control_socket=None):
    InjectionBasedControlFlow.__init__(topology, control_socket=control_socket)
    # TODO(cs): future feature: allow the user to interactively choose the order
    # events occur for each round, whether to delay, drop packets, fail nodes,
    # etc.
    # self.failure_lvl = [
    #   NOTHING,    # Everything is handled by the random number generator
    #   CRASH,      # The user only controls node crashes and restarts
    #   DROP,       # The user also controls message dropping
    #   DELAY,      # The user also controls message delays
    #   EVERYTHING  # The user controls everything, including message ordering
    # ]

  def incremement_round():
    # TODO(cs): print out the state of the network at each timestep? Take a
    # verbose flag..
    self.invariant_check_prompt()
    self.dataplane_trace_prompt()
    answer = msg.raw_input('Continue to next round? [Yn]').strip()
    if answer != '' and answer.lower() != 'y':
      self.stop()
      break
  
  def invariant_check_prompt(self):
    answer = msg.raw_input('Check Invariants? [Ny]')
    if answer != '' and answer.lower() != 'n':
      msg.interactive("Which one?")
      msg.interactive("  'l' - loops")
      msg.interactive("  'b' - blackholes")
      msg.interactive("  'r' - routing consistency")
      msg.interactive("  'c' - connectivity")
      msg.interactive("  'o' - omega")
      answer = msg.raw_input("> ")
      result = None
      if answer.lower() == 'l':
        result = self.invariant_checker.check_loops()
      elif answer.lower() == 'b':
        result = self.invariant_checker.check_blackholes()
      elif answer.lower() == 'r':
        result = self.invariant_checker.check_routing_consistency()
      elif answer.lower() == 'c':
        result = self.invariant_checker.check_connectivity()
      elif answer.lower() == 'o':
        result = self.invariant_checker.check_correspondence(self.live_switches,
                                                             self.live_links,
                                                             self.access_links)
      else:
        log.warn("Unknown input...")

      if result is None:
        return
      else:
        msg.interactive("Result: %s" % str(result))

  def dataplane_trace_prompt(self):
    if self.dataplane_trace:
      while True:
        answer = msg.raw_input('Feed in next dataplane event? [Ny]')
        if answer != '' and answer.lower() != 'n':
          self.inject_trace_event()
        else:
          break

# ----------- Old command line args ----------------
# TODO(cs): add argument for trace injection interval
#parser.add_argument("-C", "--check-interval", type=int,
#                    help='Run correspondence checking every C timesteps (assume -n)',
#                    dest="check_interval", default=35)
#parser.add_argument("-D", "--delay", type=float, metavar="time",
#                    default=0.1,
#                    help="delay in seconds for non-interactive simulation steps")
#
#parser.add_argument("-R", "--random-seed", type=float, metavar="rnd",
#                    help="Seed for the pseduo random number generator", default=0.0)
#
#parser.add_argument("-s", "--steps", type=int, metavar="nsteps",
#                    help="number of steps to simulate", default=None)
#parser.add_argument("-f", "--fuzzer-params", default="fuzzer_params.cfg",
#                    help="optional parameters for the fuzzer (e.g. fail rate)")
