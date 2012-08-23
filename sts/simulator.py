class Replayer(object):
  # TODO docstring
  # TODO this could be a partial function!
  def __init__(self, dag):
    self.dag = dag

  def run(self, simulation):
    for pruned_event in dag.events():
      for event in dag.events(pruned_event):
        event.run(simulation)

class Exerciser(object):
  # TODO docstring
  pass
