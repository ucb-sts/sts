'''
control flow type for running the simulation forward.
  - Interactive: presents an interactive prompt for injecting events and
    checking for invariants at the users' discretion
'''

from sts.topology import BufferedPatchPanel
from sts.util.console import msg, color
from sts.replay_event import *

from sts.control_flow.base import ControlFlow, RecordingSyncCallback

log = logging.getLogger("interactive")

import code
import sys
import types
import re

import readline
readline.parse_and_bind('tab:complete')

class STSCommandArg(object):
  def __init__(self, name, help_msg=None, values=None):
    self.name = name
    self.help_msg = help_msg
    self._values = values

  def arg_help(self):
    if self.help_msg:
      return help_msg
    elif self._values:
      return "one of %s" % (", ".join(map(lambda x: str(x), self.values())))

  def values(self):
    if self._values is None:
      return None
    elif isinstance(self._values, (list, tuple)):
      return self._values
    else:
      return self._values()



class STSCommand(object):
  def __init__(self, func, name, alias, help_msg):
    self.func = func
    self.name = name
    self.alias = alias
    self.help_msg = help_msg
    self.args = []

  def arg(self, name, help_msg=None, values=None):
    self.args.append(STSCommandArg(name, help_msg, values))

  def arg_help(self):
    return [ "  <%s>: %s"%(a.name, a.arg_help()) for a in self.args if a.arg_help() ]

  def get_help(self):
    name_with_args = "%s" % self.name + \
        (" " + (" ".join(map(lambda a: "<%s>" % a.name, self.args))) if self.args else "")
    aliases = ("["+self.alias+"]" if self.alias else "")
    help_msg = (self.help_msg if self.help_msg else "")
    args_help = ("\n" + "\n".join(self.arg_help()) if self.arg_help() else "")

    return "%-24s %-8s %s%s" % (name_with_args, aliases, help_msg, args_help)

class STSRegisteredObject(object):
  def __init__(self, obj, name, alias, help_msg):
    self.obj = obj
    self.name = name
    self.alias = alias
    self.help_msg = help_msg
    self.args = []

  def get_help(self):
    return "%s\t" % self.name + \
      ("["+self.alias+"]" if self.alias else "") + "\t" + \
      (self.help_msg if self.help_msg else "")


class STSConsole(object):
  def __init__(self, default_command=None):
    self.call_env = {}
    self.help_items = []
    self.commands = {}
    self._default_command = default_command

    self.cmd(self.show_help, "help", alias='h', help_msg="This help screen")

  @property
  def default_command(self):
    if not self._default_command:
      return None
    elif isinstance(self._default_command, str):
      return self._default_command
    else:
      return self._default_command()

  def show_help(self, command=None):
    if command:
      if command in self.commands:
        print "==================== Command %s ========================" % command
        print self.commands[command].get_help()
      else:
        print "Command %s not found" % command
    else:
      print "==================== Command help ========================"
      for item in self.help_items:
        if isinstance(item, str):
          print item
        else:
          print item.get_help()

  def cmd_group(self, name):
    self.help_items.append("\n%s %s %s" % ("-" * ((80-len(name))/2), name, '-' * ((80-len(name))/2) ))

  def _register(self, func, name, alias=None):
    self.call_env[name] = func
    if alias:
      for key in alias.split('|'):
        self.call_env[key] = func

  def cmd(self, func, name, alias=None, help_msg=None):
    self._register(func, name, alias)
    command = STSCommand(func, name, alias, help_msg)
    self.commands[name] = command
    if alias:
      for key in alias.split('|'):
        self.commands[key] = command
    self.help_items.append(command)
    command.get_help()
    return command

  def register_obj(self, obj, name, alias=None, help_msg=None):
    self._register(obj, name, alias)
    obj = STSRegisteredObject(obj, name, alias, help_msg)
    self.help_items.append(obj)

  def autocomplete_matches(self, text, index):
    if index == 0:
      return [ s for s in self.call_env.keys() if s.startswith(text) ]
    else:
      """ 
      if parts[0] in self.commands:
        command = self.commands[parts[0]]
        argno = len(parts) - 2
        argval = parts[-1]
        if argno < len(command.args):
          return [ s for s in self.args[argo].values() if s.startswith(argval) ]
      """
      return []

  def run(self):
    local = self.call_env
    def completer(text, state):
      try:
        matches = self.autocomplete_matches(text, readline.get_begidx())
        if state < len(matches):
            return matches[state]
        else:
            return None
      except BaseException as e:
        print "Error on autocompleting: %s" % e
        raise e

    readline.set_completer(completer)
    digits = re.compile(r'\d+')
    quoted = re.compile(r'".*"|\'.*\'')

    def quote_parameter(s):
      if quoted.match(s):
        return s
      elif digits.match(s):
        return s
      else:
        return "'%s'" % s.replace("'", "\\'")

    def input(prompt):
      if self.default_command:
        prompt = prompt + color.GRAY + "["+ self.default_command + "]" + color.WHITE + " >"
      else:
        prompt = prompt + " >"
      x = msg.raw_input(prompt)
      if x == "" and self.default_command:
        x = self.default_command

      parts = x.split(" ")
      cmd_name = parts[0]
      if cmd_name in self.commands:
        x = parts[0]+"(" + ", ".join(map(lambda s: quote_parameter(s), parts[1:])) + ")"
      return x

    sys.ps1 = color.GREEN + "STS " + color.WHITE
    code.interact(color.GREEN + "STS Interactive console."+color.WHITE+"\nPython expressions and sts commands supported.\nType 'help' for an overview of available commands.\n", input, local=local)

class Interactive(ControlFlow):
  '''
  Presents an interactive prompt for injecting events and
  checking for invariants at the users' discretion
  '''
  # TODO(cs): rather than just prompting "Continue to next round? [Yn]", allow
  #           the user to examine the state of the network interactively (i.e.,
  #           provide them with the normal POX cli + the simulated events
  def __init__(self, simulation_cfg, input_logger=None):
    ControlFlow.__init__(self, simulation_cfg)
    self.sync_callback = RecordingSyncCallback(input_logger)
    self.logical_time = 0
    self._input_logger = input_logger
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

  def _log_input_event(self, event, **kws):
    # TODO(cs): redundant with Fuzzer._log_input_event
    if self._input_logger is not None:
      self._input_logger.log_input_event(event, **kws)

  def simulate(self):
    self.simulation = self.simulation_cfg.bootstrap(self.sync_callback)
    self._forwarded_this_step = 0
    try:
      c = STSConsole(default_command=self.default_command)
      c.cmd_group("Simulation state")
      c.cmd(self.next_step, "next", alias="n", help_msg="Proceed to next simulation step")
      c.cmd(self.quit, "quit", alias="q", help_msg="Quit the simulation")

      c.cmd_group("Invariants")
      c.cmd(self.invariant_check, "check_invariants", alias="inv",  help_msg="Run an invariant check").arg("kind", values=['omega', 'connectivity', 'loops', 'liveness'])

      c.cmd_group("Dataplane")
      c.cmd(self.dataplane_trace_feed, "dp_inject",  alias="dpi", help_msg="Inject the next dataplane event from the trace")
      c.cmd(self.dataplane_forward,    "dp_forward", alias="dpf", help_msg="Forward a pending dataplane event")
      c.cmd(self.dataplane_drop,       "dp_drop",    alias="dpd", help_msg="Drop a pending dataplane event")
      c.cmd(self.dataplane_delay,      "dp_delay",   alias="dpe", help_msg="Delay a pending dataplane event")

      c.cmd_group("Controlling entitities")
      c.cmd(self.list_controllers, "list_controllers", alias="lsc", help_msg="List controllers")
      c.cmd(self.kill_controller,  "kill_controller",  alias="kc", help_msg="Kill a controller").arg("label", values=lambda: map(lambda c: c.label, self.simulation.controller_manager.live_controllers))
      c.cmd(self.start_controller,  "start_controller",  alias="sc", help_msg="Restart a controller").arg("label", values=lambda: map(lambda c: c.label, self.simulation.controller_manager.down_controllers))
      c.cmd(self.list_switches, "list_switches", alias="lss", help_msg="List switches")
      c.cmd(self.kill_switch,  "kill_switch", alias="ks", help_msg="Kill a switch").arg("dpid", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))
      c.cmd(self.start_switch,  "start_switch", alias="ss", help_msg="Restart a switch").arg("dpid", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))

      c.cmd_group("Python objects")
      c.register_obj(self.simulation, "simulation", help_msg="access the simulation object")
      c.register_obj(self.simulation.topology, "topology", alias="topo", help_msg="access the topology object")
      c.run()
    finally:
      if self._input_logger is not None:
        self._input_logger.close(self.simulation_cfg)

  def default_command(self):
    queued = self.simulation.patch_panel.queued_dataplane_events
    if len(queued) == 1 and self._forwarded_this_step == 0 and self.simulation.topology.ok_to_send(queued[0]):
      return "dpf"
    else:
      return "next"

  def quit(self):
    print "End console with CTRL-D"

  def next_step(self):
    self.check_message_receipts()
    time.sleep(0.05)
    self.logical_time += 1
    self._forwarded_this_step = 0
    print "-------------------"
    print "Advanced to step %d" % self.logical_time
    self.show_queued_events()

  def show_queued_events(self):
    queued = self.simulation.patch_panel.queued_dataplane_events
    if len(queued) > 0:
      print "Queued Dataplane events:"
      for (i, e) in enumerate(queued):
        print "%d: %s on %s:%s" % (i, e, e.node, e.port)

  def list_controllers(self):
    cm = self.simulation.controller_manager
    live = cm.live_controllers
    print "Controllers:"
    for c in cm.controllers:
      print "%s %s %s %s" % (c.label, c.uuid, repr(c), "[ALIVE]" if c in live else "[DEAD]")

  def kill_controller(self, label):
    cm = self.simulation.controller_manager
    c = cm.get_controller_by_label(label)
    if c:
      print "Killing controller: %s %s" % (label, repr(c))
      cm.kill_controller(c)
      self._log_input_event(ControllerFailure(c.uuid))
    else:
      print "Controller with label %s not found" %label

  def start_controller(self, label):
    cm = self.simulation.controller_manager
    c = cm.get_controller_by_label(label)
    if c:
      print "Killing controller: %s %s" % (label, repr(c))
      cm.reboot_controller(c)
      self._log_input_event(ControllerRecovery(c.uuid))
    else:
      print "Controller with label %s not found" %label

  def list_switches(self):
    topology = self.simulation.topology
    live = topology.live_switches
    print "Switches:"
    for s in topology.switches:
      print "%d %s %s" % (s.dpid, repr(s), "[ALIVE]" if s in live else "[DEAD]")

  def kill_switch(self, dpid):
    topology = self.simulation.topology
    switch = topology.get_switch(dpid)
    topology.crash_switch(switch)
    self._log_input_event(SwitchFailure(switch.dpid))

  def start_switch(self, dpid):
    topology = self.simulation.topology
    switch = topology.get_switch(dpid)
    topology.recover_switch(switch, down_controller_ids=map(lambda c: c.uuid, self.simulation.controller_manager.down_controllers))
    self._log_input_event(SwitchRecovery(switch.dpid))

  def invariant_check(self, kind):
    if kind == "omega":
      self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_correspondence))
      result = InvariantChecker.check_correspondence(self.simulation)
      message = "Controllers with miscorrepondence: "
    elif kind == "connectivity":
      self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_connectivity))
      result = self.invariant_checker.check_connectivity(self.simulation)
      message = "Disconnected host pairs: "
    elif kind == "loops":
      self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_loops))
      result = self.invariant_checker.check_loops(self.simulation)
      message = "Loops: "
    elif kind == "liveness":
      self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_liveness))
      result = self.invariant_checker.check_loops(self.simulation)
      message = "Crashed controllers: "
    else:
      log.warn("Unknown invariant kind...")

  def dataplane_trace_feed(self):
    if self.simulation.dataplane_trace:
      dp_event = self.simulation.dataplane_trace.inject_trace_event()
      self._log_input_event(TrafficInjection(), dp_event=dp_event)

  def _select_dataplane_event(self, sel=None):
     queued = self.simulation.patch_panel.queued_dataplane_events
     if not sel:
       if len(queued) == 1:
         return queued[0]
       else:
         print "Multiple events queued -- please select one"
         return None
     else:
       return queued[sel]

  def dataplane_forward(self, event=None):
    dp_event = self._select_dataplane_event(event)
    if not dp_event:
      return

    if self.simulation.topology.ok_to_send(dp_event):
      self.simulation.patch_panel.permit_dp_event(dp_event)
      self._log_input_event(DataplanePermit(dp_event.fingerprint))
      self._forwarded_this_step += 1
    else:
      print "Not ready to send event %s" % event

  def dataplane_drop(self, event=None):
    dp_event = self._select_dataplane_event(event)
    if not dp_event:
      return
    self.simulation.patch_panel.drop_dp_event(dp_event)
    self._log_input_event(DataplaneDrop(dp_event.fingerprint))

  def dataplane_delay(self, event=None):
    dp_event = self._select_dataplane_event(event)
    if not dp_event:
      return
    self.simulation.patch_panel.delay_dp_event(dp_event)

  def loop(self):
    try:
      while True:
        # TODO(cs): print out the state of the network at each timestep? Take a
        # verbose flag..
        time.sleep(0.05)
        self.logical_time += 1
        self.invariant_check_prompt()
        self.dataplane_trace_prompt()
        self.check_dataplane()
        self.check_message_receipts()
        answer = msg.raw_input('Continue to next round? [Yn]').strip()
        if answer != '' and answer.lower() != 'y':
          break
    finally:
      if self._input_logger is not None:
        self._input_logger.close(self.simulation_cfg)

  def invariant_check_prompt(self):
    answer = msg.raw_input('Check Invariants? [Ny]')
    if answer != '' and answer.lower() != 'n':
      msg.interactive("Which one?")
      msg.interactive("  'o' - omega")
      msg.interactive("  'c' - connectivity")
      msg.interactive("  'lo' - loops")
      msg.interactive("  'li' - controller liveness")
      answer = msg.raw_input("> ")
      result = None
      message = ""
      if answer.lower() == 'o':
        self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_correspondence))
        result = InvariantChecker.check_correspondence(self.simulation)
        message = "Controllers with miscorrepondence: "
      elif answer.lower() == 'c':
        self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_connectivity))
        result = self.invariant_checker.check_connectivity(self.simulation)
        message = "Disconnected host pairs: "
      elif answer.lower() == 'lo':
        self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_loops))
        result = self.invariant_checker.check_loops(self.simulation)
        message = "Loops: "
      elif answer.lower() == 'li':
        self._log_input_event(CheckInvariants(invariant_check=InvariantChecker.check_liveness))
        result = self.invariant_checker.check_loops(self.simulation)
        message = "Crashed controllers: "
      else:
        log.warn("Unknown input...")

      if result is None:
        return
      else:
        msg.interactive("%s: %s" % (message, str(result)))

  def dataplane_trace_prompt(self):
    if self.simulation.dataplane_trace:
      while True:
        answer = msg.raw_input('Feed in next dataplane event? [Ny]')
        if answer != '' and answer.lower() != 'n':
          dp_event = self.simulation.dataplane_trace.inject_trace_event()
          self._log_input_event(TrafficInjection(), dp_event=dp_event)
        else:
          break

  def check_dataplane(self):
    ''' Decide whether to delay, drop, or deliver packets '''
    if type(self.simulation.patch_panel) == BufferedPatchPanel:
      for dp_event in self.simulation.patch_panel.queued_dataplane_events:
        answer = msg.raw_input('Allow [a], Drop [d], or Delay [e] dataplane packet %s? [Ade]' %
                               dp_event)
        if ((answer == '' or answer.lower() == 'a') and
                self.simulation.topology.ok_to_send(dp_event)):
          self.simulation.patch_panel.permit_dp_event(dp_event)
          self._log_input_event(DataplanePermit(dp_event.fingerprint))
        elif answer.lower() == 'd':
          self.simulation.patch_panel.drop_dp_event(dp_event)
          self._log_input_event(DataplaneDrop(dp_event.fingerprint))
        elif answer.lower() == 'e':
          self.simulation.patch_panel.delay_dp_event(dp_event)
        else:
          log.warn("Unknown input...")
          self.simulation.patch_panel.delay_dp_event(dp_event)

  def check_message_receipts(self):
    for pending_receipt in self.simulation.god_scheduler.pending_receives():
      # For now, just schedule FIFO.
      # TODO(cs): make this interactive
      self.simulation.god_scheduler.schedule(pending_receipt)
      self._log_input_event(ControlMessageReceive(pending_receipt.dpid,
                                                  pending_receipt.controller_id,
                                                  pending_receipt.fingerprint))

  # TODO(cs): add support for control channel blocking + switch, link,
  # controller failures, host migration, god scheduling

