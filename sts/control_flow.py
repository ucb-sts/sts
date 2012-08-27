class Replayer(object):
  # TODO docstring
  def __init__(self, dag):
    self.dag = dag

  def run(self, simulation):
    def increment_round():
      simulation.forward_data()
      # TODO more stuff to forward round?
    for pruned_event in dag.events():
      for event in dag.events(pruned_event):
        event.run(simulation)
        self.increment_round(simulation)

class Exerciser(object):
  # TODO docstring
  def increment_round(self):
    pass # TODO do something fancy here!

class Interactive(object):
  pass


# TODO: add argument for trace injection interval
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
