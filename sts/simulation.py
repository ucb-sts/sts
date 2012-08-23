class Simulation(object):
  # TODO docstring
  def __init__(self, topology):
    self.topology = topology
    self.processes = {} # k=process name, v=Popen object

  def increment_round(self):
    pass # TODO move from god object method
