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
