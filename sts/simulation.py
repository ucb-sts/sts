class Simulation(object):
  # TODO docstring
  def __init__(self, topology):
    self.topology = topology
    self.processes = {} # k=process name, v=Popen object
  # TODO add things in here to delegate to topology

  def forward_data(self, dataplane=True, controlplane=True):
    pass # TODO implement this to affect the topology
