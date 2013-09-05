# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''
control flow type for running the simulation forward.
  - Interactive: presents an interactive prompt for injecting events and
    checking for invariants at the users' discretion
'''

from sts.simulation_state import default_boot_controllers
from sts.util.tabular import Tabular
from sts.util.procutils import printlock
from sts.util.console import color
from sts.replay_event import *
from sts.util.convenience import find
from sts.traffic_generator import TrafficGenerator
from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.udp import *
from pox.lib.packet.icmp import *
import pox.openflow.libopenflow_01 as of

from sts.control_flow.base import ControlFlow, RecordingSyncCallback
from sts.invariant_checker import InvariantChecker

log = logging.getLogger("interactive")

import code
import sys
import re
import random

try:
  import readline
  readline.parse_and_bind('tab: complete')
except:
  log.critical("Need to install readline: $ sudo pip install readline")

class STSCommandArg(object):
  def __init__(self, name, help_msg=None, values=None):
    self.name = name
    self.help_msg = help_msg
    self._values = values

  def arg_help(self):
    if self.help_msg:
      return self.help_msg
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
    return self

  def arg_help(self):
    return [ "  <%s>: %s"%(a.name, a.arg_help()) for a in self.args if a.arg_help() ]

  def get_help(self):
    name_with_args = "%s %s" % (self.name, " ".join(map(lambda a: "<%s>" % a.name, self.args)) if self.args else "")
    alias = "[%s]" % self.alias if self.alias else ""
    help_msg = self.help_msg if self.help_msg else ""
    args_help = "\n" + "\n".join(self.arg_help()) if self.arg_help() else ""
    return "{0:34}{1:8}{2:20}{3:20}".format(name_with_args, alias, help_msg, args_help)

class STSRegisteredObject(object):
  def __init__(self, obj, name, alias, help_msg):
    self.obj = obj
    self.name = name
    self.alias = alias
    self.help_msg = help_msg
    self.args = []

  def get_help(self):
    name = self.name
    alias = "[%s]" % self.alias if self.alias else ""
    help_msg = self.help_msg if self.help_msg else ""
    return "{0:34}{1:8}{2:20}".format(name, alias, help_msg)

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
        name = "Command %s" % command
        print "%s %s %s" % ("=" * ((90-len(name))/2), name, '=' * ((90-len(name))/2) )
        print self.commands[command].get_help()
      else:
        print "Command %s not found" % command
    else:
      name = "Command Help"
      print "%s %s %s" % ("=" * ((90-len(name))/2), name, '=' * ((90-len(name))/2) )
      for item in self.help_items:
        if isinstance(item, str):
          print item
        else:
          print item.get_help()

  def cmd_group(self, name):
    self.help_items.append("\n%s %s %s" % ("-" * ((90-len(name))/2), name, '-' * ((90-len(name))/2) ))

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
        prompt = prompt + "> "
      with printlock:
        x = msg.raw_input(prompt)
      if x == "" and self.default_command:
        x = self.default_command

      parts = x.split(" ")
      cmd_name = parts[0]
      if cmd_name in self.commands:
        x = parts[0]+"(" + ", ".join(map(lambda s: quote_parameter(s), parts[1:])) + ")"
      return x

    sys.ps1 = color.GREEN + "STS " + color.WHITE
    if hasattr(sys, "_orig_stdout"):
      patched_stdout = sys.stdout
      sys.stdout = sys._orig_stdout
    else:
      patched_stdout = None

    code.interact(color.GREEN + "STS Interactive console."+color.WHITE+"\nPython expressions and sts commands supported.\nType 'help' for an overview of available commands.\n", input, local=local)

    if patched_stdout:
      sys.stdout = patched_stdout

class Interactive(ControlFlow):
  '''
  Presents an interactive prompt for injecting events and
  checking for invariants at the users' discretion
  '''
  def __init__(self, simulation_cfg, input_logger=None):
    ControlFlow.__init__(self, simulation_cfg)
    self.sync_callback = RecordingSyncCallback(input_logger)
    self.logical_time = 0
    self._input_logger = input_logger
    self.traffic_generator = TrafficGenerator(random.Random())
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
      event.round = self.logical_time
      self._input_logger.log_input_event(event, **kws)

  def init_results(self, results_dir):
    if self._input_logger is not None:
      self._input_logger.open(results_dir)

  def default_connect_to_controllers(self, simulation):
    simulation.connect_to_controllers()
    self._log_input_event(ConnectToControllers())

  def simulate(self, simulation=None, boot_controllers=default_boot_controllers,
               connect_to_controllers=None,
               bound_objects=()):
    if simulation is None:
      self.simulation = self.simulation_cfg.bootstrap(self.sync_callback,
                                                      boot_controllers=boot_controllers)
      if connect_to_controllers is None:
        self.default_connect_to_controllers(self.simulation)
      else:
        connect_to_controllers(self.simulation)
    else:
      self.simulation = simulation

    self._forwarded_this_step = 0
    self.traffic_generator.set_topology(self.simulation.topology)
    try:
      c = STSConsole(default_command=self.default_command)
      c.cmd_group("Simulation State")
      c.cmd(self.next_step,             "next",             alias="n",      help_msg="Proceed to next simulation step")
      c.cmd(self.quit,                  "quit",             alias="q",      help_msg="Quit the simulation")

      c.cmd_group("Invariants")
      c.cmd(self.invariant_check,       "check_invariants", alias="inv",    help_msg="Run an invariant check")\
          .arg("kind", values=['omega', 'connectivity', 'loops', 'liveness', "python_connectivity", "blackholes"])

      c.cmd_group("Dataplane")
      c.cmd(self.dataplane_trace_feed,  "dp_inject",        alias="dpi",    help_msg="Inject the next dataplane event from the trace")
      c.cmd(self.dataplane_ping,        "dp_ping",          alias="dpp",    help_msg="Generate and inject a new ping packet")
      c.cmd(self.dataplane_forward,     "dp_forward",       alias="dpf",    help_msg="Forward a pending dataplane event")
      c.cmd(self.dataplane_drop,        "dp_drop",          alias="dpd",    help_msg="Drop a pending dataplane event")
      c.cmd(self.dataplane_delay,       "dp_delay",         alias="dpe",    help_msg="Delay a pending dataplane event")

      c.cmd_group("Controlling Entitities")
      c.cmd(self.list_controllers,  "list_controllers",     alias="lsc",    help_msg="List controllers")
      c.cmd(self.kill_controller,   "kill_controller",      alias="kc",     help_msg="Kill a controller")\
          .arg("label", values=lambda: map(lambda c: c.label, self.simulation.controller_manager.live_controllers))
      c.cmd(self.start_controller,  "start_controller",     alias="sc",     help_msg="Restart a controller")\
          .arg("label", values=lambda: map(lambda c: c.label, self.simulation.controller_manager.down_controllers))
      c.cmd(self.list_switches,     "list_switches",        alias="lss",    help_msg="List switches")
      c.cmd(self.kill_switch,       "kill_switch",          alias="ks",     help_msg="Kill a switch")\
          .arg("dpid", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))
      c.cmd(self.start_switch,      "start_switch",         alias="ss",     help_msg="Restart a switch")\
          .arg("dpid", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))
      c.cmd(self.cut_link,          "cut_link",             alias="cl",     help_msg="Cut a link")\
          .arg("dpid1", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))\
          .arg("dpid2", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))
      c.cmd(self.repair_link,       "repair_link",          alias="rl",     help_msg="Repair a link")\
          .arg("dpid1", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))\
          .arg("dpid2", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))
      c.cmd(self.show_flow_table,   "show_flows",           alias="sf",     help_msg="Show flowtable of a switch")\
          .arg("dpid", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))
      c.cmd(self.list_hosts,        "list_hosts",           alias="lhs",    help_msg="List hosts")
      c.cmd(self.migrate_host,      "migrate_host",         alias="mh",     help_msg="Migrate a host to switch dpid")\
          .arg("hid", values=lambda: map(lambda h: h.hid, self.simulation.topology.hosts))\
          .arg("dpid", values=lambda: map(lambda s: s.dpid, self.simulation.topology.switches))

      c.cmd_group("Python Objects")
      c.register_obj(self.simulation,           "simulation", alias="sim",  help_msg="access the simulation object")
      c.register_obj(self.simulation.topology,  "topology",   alias="topo", help_msg="access the topology object")
      for (name, obj) in bound_objects:
        c.register_obj(obj, name, help_msg="access the %s object" % name)

      c.run()
    finally:
      if self._input_logger is not None:
        self._input_logger.close(self, self.simulation_cfg)
    return self.simulation

  def default_command(self):
    queued = self.simulation.patch_panel.queued_dataplane_events
    if len(queued) == 1 and self._forwarded_this_step == 0 and self.simulation.topology.ok_to_send(queued[0]):
      return "dpf"
    else:
      return "next"

  def quit(self):
    print "End console with CTRL-D"

  def next_step(self):
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
      print "%s %s %s %s" % (c.label, c.cid, repr(c), "[ALIVE]" if c in live else "[DEAD]")

  def kill_controller(self, label):
    cm = self.simulation.controller_manager
    c = cm.get_controller_by_label(label)
    if c:
      print "Killing controller: %s %s" % (label, repr(c))
      cm.kill_controller(c)
      self._log_input_event(ControllerFailure(c.cid))
    else:
      print "Controller with label %s not found" %label

  def start_controller(self, label):
    cm = self.simulation.controller_manager
    c = cm.get_controller_by_label(label)
    if c:
      print "Killing controller: %s %s" % (label, repr(c))
      cm.reboot_controller(c)
      self._log_input_event(ControllerRecovery(c.cid))
    else:
      print "Controller with label %s not found" %label

  def list_switches(self):
    topology = self.simulation.topology
    live = topology.live_switches
    print "Switches:"
    for s in topology.switches:
      print "%d %s %s" % (s.dpid, repr(s), "[ALIVE]" if s in live else "[DEAD]")

  def list_hosts(self):
    topology = self.simulation.topology
    print "Hosts:"
    for h in topology.hosts:
      print "%d %s" % (h.hid, str(h),)

  def kill_switch(self, dpid):
    topology = self.simulation.topology
    switch = topology.get_switch(dpid)
    topology.crash_switch(switch)
    self._log_input_event(SwitchFailure(switch.dpid))

  def start_switch(self, dpid):
    topology = self.simulation.topology
    switch = topology.get_switch(dpid)
    down_controller_ids = map(lambda c: c.cid, self.simulation.controller_manager.down_controllers)
    topology.recover_switch(switch, down_controller_ids=down_controller_ids)
    self._log_input_event(SwitchRecovery(switch.dpid))

  def cut_link(self, dpid1, dpid2):
    topology = self.simulation.topology
    link = topology.get_link(dpid1, dpid2)
    topology.sever_link(link)
    self._log_input_event(LinkFailure(
                          link.start_software_switch.dpid,
                          link.start_port.port_no,
                          link.end_software_switch.dpid,
                          link.end_port.port_no))

  def repair_link(self, dpid1, dpid2):
    topology = self.simulation.topology
    link = topology.get_link(dpid1, dpid2)
    topology.repair_link(link)
    self._log_input_event(LinkRecovery(
                          link.start_software_switch.dpid,
                          link.start_port.port_no,
                          link.end_software_switch.dpid,
                          link.end_port.port_no))

  def migrate_host(self, hid, dpid):
    topology = self.simulation.topology
    host = topology.get_host(hid)
    # TODO(cs): make this lookup more efficient
    access_link = find(lambda a: a.host == host, topology.access_links)
    old_ingress_dpid = access_link.switch.dpid
    old_ingress_port_no = access_link.switch_port.port_no
    new_switch = topology.get_switch(dpid)
    new_port_no = max(new_switch.ports.keys()) + 1
    self.simulation.topology.migrate_host(old_ingress_dpid,
                                          old_ingress_port_no,
                                          dpid,
                                          new_port_no)
    self._log_input_event(HostMigration(old_ingress_dpid,
                                        old_ingress_port_no,
                                        dpid,
                                        new_port_no,
                                        access_link.host.hid))
    self._send_initialization_packet(access_link.host, send_to_self=True)

  # TODO(cs): ripped directly from fuzzer. Redundant!
  def _send_initialization_packet(self, host, send_to_self=False):
    traffic_type = "icmp_ping"
    dp_event = self.traffic_generator.generate_and_inject(traffic_type, host, send_to_self=send_to_self)
    self._log_input_event(TrafficInjection(dp_event=dp_event, host_id=host.hid))

  def show_flow_table(self, dpid):
    topology = self.simulation.topology
    switch = topology.get_switch(dpid)

    dl_types = { 0x0800: "IP",
                 0x0806: "ARP",
                 0x8100: "VLAN",
                 0x88cc: "LLDP",
                 0x888e: "PAE"
                 }
    nw_protos = { 1 : "ICMP", 6 : "TCP", 17 : "UDP" }

    ports = { v: k.replace("OFPP_","") for (k,v) in of.ofp_port_rev_map.iteritems() }

    def dl_type(e):
      d = e.match.dl_type
      if d is None:
        return d
      else:
        return dl_types[d] if d in dl_types else "%x" %d

    def nw_proto(e):
      p = e.match.nw_proto
      return nw_protos[p] if p in nw_protos else p

    def action(a):
      if isinstance(a, ofp_action_output):
        return ports[a.port] if a.port in ports else "output(%d)" % a.port
      else:
        return str(a)
    def actions(e):
      if len(e.actions) == 0:
        return "(drop)"
      else:
        return ", ".join(action(a) for a in e.actions)

    t = Tabular( ("Prio", lambda e: e.priority),
                ("in_port", lambda e: e.match.in_port),
                ("dl_type", dl_type),
                ("dl_src", lambda e: e.match.dl_src),
                ("dl_dst", lambda e: e.match.dl_dst),
                ("nw_proto", nw_proto),
                ("nw_src", lambda e: e.match.nw_src),
                ("nw_dst", lambda e: e.match.nw_dst),
                ("tp_src", lambda e: e.match.tp_src),
                ("tp_dst", lambda e: e.match.tp_dst),
                ("actions", actions),
                )
    t.show(switch.table.entries)

  def invariant_check(self, kind):
    if kind == "omega" or kind == "o":
      self._log_input_event(CheckInvariants(round=self.logical_time, invariant_check_name="InvariantChecker.check_correspondence"))
      result = InvariantChecker.check_correspondence(self.simulation)
      message = "Controllers with miscorrepondence: "
    elif kind == "connectivity" or kind == "c":
      self._log_input_event(CheckInvariants(round=self.logical_time, invariant_check_name="InvariantChecker.check_connectivity"))
      result = InvariantChecker.check_connectivity(self.simulation)
      message = "Disconnected host pairs: "
    elif kind == "python_connectivity" or kind == "pc":
      self._log_input_event(CheckInvariants(round=self.logical_time, invariant_check_name="InvariantChecker.python_check_connectivity"))
      result = InvariantChecker.python_check_connectivity(self.simulation)
      message = "Disconnected host pairs: "
    elif kind == "loops" or kind == "lo":
      self._log_input_event(CheckInvariants(round=self.logical_time, invariant_check_name="InvariantChecker.check_loops"))
      result = InvariantChecker.python_check_loops(self.simulation)
      message = "Loops: "
    elif kind == "liveness" or kind == "li":
      self._log_input_event(CheckInvariants(round=self.logical_time, invariant_check_name="InvariantChecker.check_liveness"))
      result = InvariantChecker.check_liveness(self.simulation)
      message = "Crashed controllers: "
    elif kind == "blackholes" or kind == "bl":
      self._log_input_event(CheckInvariants(round=self.logical_time, invariant_check_name="InvariantChecker.check_blackholes"))
      result = InvariantChecker.python_check_blackholes(self.simulation)
      message = "Blackholes: "
    else:
      log.warn("Unknown invariant kind...")
    self.simulation.violation_tracker.track(result, self.logical_time)
    persistent_violations = self.simulation.violation_tracker.persistent_violations
    transient_violations = list(set(result) - set(persistent_violations))

    msg.interactive(message + str(result))
    if transient_violations != []:
      self._log_input_event(InvariantViolation(transient_violations))
    if persistent_violations != []:
      msg.fail("Persistent violations detected!: %s"
               % str(persistent_violations))
      self._log_input_event(InvariantViolation(persistent_violations, persistent=True))

  def dataplane_trace_feed(self):
    if self.simulation.dataplane_trace:
      (dp_event, host) = self.simulation.dataplane_trace.inject_trace_event()
      self._log_input_event(TrafficInjection(dp_event=dp_event, host=host.hid))
    else:
      print "No dataplane trace to inject from."

  def dataplane_ping(self, from_hid=None, to_hid=None):
    if (from_hid is not None) and \
       (from_hid not in self.simulation.topology.hid2host.keys()):
      print "Unknown host %s" % from_hid
      return
    if (to_hid is not None) and \
       (to_hid not in self.simulation.topology.hid2host.keys()):
      print "Unknown host %s" % to_hid
      return
    dp_event = self.traffic_generator.generate_and_inject("icmp_ping", from_hid, to_hid,
                                    payload_content=raw_input("Enter payload content:\n"))
    self._log_input_event(TrafficInjection(dp_event=dp_event))

  def _select_dataplane_event(self, sel=None):
    queued = self.simulation.patch_panel.queued_dataplane_events
    if len(queued) == 0:
      print "No dataplane events queued."
      return None
    if not sel:
      return queued[0]
    if sel >= len(queued):
      print "Given index out of bounds. Try a value smaller than %d" % len(queued)
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
    self._log_input_event(DataplaneDrop(dp_event.fingerprint,
                                        host_id=dp_event.get_host_id(),
                                        dpid=dp_event.get_switch_id()))

  def dataplane_delay(self, event=None):
    dp_event = self._select_dataplane_event(event)
    if not dp_event:
      return
    self.simulation.patch_panel.delay_dp_event(dp_event)

  # TODO(cs): add support for control channel blocking + link,
  # controller failures, god scheduling
