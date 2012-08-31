import pickle

class Trace(object):
  '''Encapsulates a sequence of dataplane events to inject into a simulated network.'''

  def __init__(self, tracefile_path, topology):
    with file(tracefile_path, 'r') as tracefile:
      self.dataplane_trace = pickle.load(tracefile)

    # Hashmap used to inject packets from the dataplane_trace
    self.interface2host = {
      interface: host
      for host in topology.hosts
      for interface in host.interfaces
    }

    self._type_check_dataplane_trace()

  def _type_check_dataplane_trace(self):
    for dp_event in self.dataplane_trace:
      if dp_event.interface not in self.interface2host:
        raise RuntimeError("Dataplane trace does not type check (%s)" %
                           str(dp_event.interface))

  def inject_trace_event(self):
    if len(self.dataplane_trace) == 0:
      log.warn("No more trace inputs to inject!")
      return
    else:
      log.info("Injecting trace input")
      dp_event = self.dataplane_trace.pop(0)
      host = self.interface2host[dp_event.interface]
      if not host:
        log.warn("Host %s not present" % str(host))
        return
      host.send(dp_event.interface, dp_event.packet)
