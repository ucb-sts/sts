import json
import itertools
import os
import dataplane_traces.trace_generator as tg

class InputLogger(object):
  '''Log input events injected by a control_flow.Fuzzer'''
  _label_gen = itertools.count(1)

  def __init__(self, output_path):
    self.output = open(output_path, 'a')
    self.dp_events = []
    self.dp_trace_path = "./dataplane_traces/" + os.path.basename(output_path)

  def log_input_event(**kws):
    # assign a label
    kws['label'] = 'e' + self._label_gen.next()
    # 'class' is a reserved keyword, so we replace 'klass' with 'class'
    # instead
    kws['class'] = kws['klass']
    del kws['klass']

    # We store dp_events in the Trace object, not the log itself
    if kws['class'] == "TrafficInjection":
      self.dp_events.append(kws['dp_event'])
      del kws['dp_event']

    json_hash = json.dumps(kws)
    self.output.write(json_hash + '\n')

  def close(self):
    self.output.close()
    if self.dp_events != []:
      tg.write_trace_log(self.dp_events, self.dp_trace_path)
    # TODO(cs): write out config file
