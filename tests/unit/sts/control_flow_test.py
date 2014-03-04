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

import unittest
import sys
import os
import signal

from config.experiment_config_lib import ControllerConfig
from sts.control_flow.replayer import Replayer
from sts.topology import FatTree, BufferedPatchPanel, MeshTopology
from sts.simulation_state import SimulationConfig
from sts.entities import Host
from sts.util.convenience import IPAddressSpace

sys.path.append(os.path.dirname(__file__) + "/../../..")

_running_simulation = None
def handle_int(sigspec, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % sigspec
  if (_running_simulation is not None and
      _running_simulation.current_simulation is not None):
    _running_simulation.current_simulation.clean_up()
  raise RuntimeError("terminating on signal %d" % sigspec)

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

class ReplayerTest(unittest.TestCase):
  tmp_basic_superlog = '/tmp/superlog_basic.tmp'
  tmp_controller_superlog = '/tmp/superlog_controller.tmp'
  tmp_dataplane_superlog = '/tmp/superlog_dataplane.tmp'
  tmp_migration_superlog = '/tmp/superlog_migration.tmp'

  # ------------------------------------------ #
  #        Basic Test                          #
  # ------------------------------------------ #

  def write_simple_superlog(self):
    ''' Make sure to delete afterwards! '''
    superlog = open(self.tmp_basic_superlog, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "start_dpid": 8, "class": "LinkFailure",'''
             ''' "start_port_no": 3, "end_dpid": 15, "end_port_no": 2,'''
             ''' "label": "e1", "time": [0,0], "round": 0}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "start_dpid": 8, "class": "LinkRecovery",'''
             ''' "start_port_no": 3, "end_dpid": 15, "end_port_no": 2, "label": "e2", "time": [0,0], "round": 0}''')
    superlog.write(e2 + '\n')
    e3 = str('''{"dependent_labels": ["e4"], "dpid": 8, "class": "SwitchFailure",'''
             ''' "label": "e3", "time": [0,0], "round": 0}''')
    superlog.write(e3 + '\n')
    e4 = str('''{"dependent_labels": [], "dpid": 8, "class": "SwitchRecovery",'''
             ''' "label": "e4", "time": [0,0], "round": 0}''')
    superlog.write(e4 + '\n')
    superlog.close()

  def setup_simple_simulation(self):
    controllers = []
    topology_class = FatTree
    topology_params = ""
    patch_panel_class = BufferedPatchPanel
    sim = SimulationConfig(controllers, topology_class, topology_params, patch_panel_class)
    global _running_simulation
    _running_simulation = sim
    return sim

  def test_basic(self):
    simulation = None
    try:
      self.write_simple_superlog()
      simulation_cfg = self.setup_simple_simulation()
      replayer = Replayer(simulation_cfg, self.tmp_basic_superlog)
      simulation = replayer.simulate()
    finally:
      os.unlink(self.tmp_basic_superlog)
      if simulation is not None:
        simulation.clean_up()

  # ------------------------------------------ #
  #        Controller Crash Test               #
  # ------------------------------------------ #

  def write_controller_crash_superlog(self):
    superlog = open(self.tmp_controller_superlog, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "controller_id": "c1",'''
             ''' "class": "ControllerFailure", "label": "e1", "time": [0,0], "round": 0}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "controller_id": "c1",'''
             ''' "class": "ControllerRecovery", "label": "e2", "time": [0,0], "round": 0}''')
    superlog.write(e2 + '\n')
    superlog.close()

  def setup_controller_simulation(self):
    start_cmd = "./pox.py --verbose --no-cli sts.syncproto.pox_syncer --blocking=False openflow.of_01 --address=__address__ --port=__port__"
    ControllerConfig._controller_labels.clear()
    IPAddressSpace._claimed_addresses.clear()
    controllers = [ControllerConfig(cwd='pox', label="c1", start_cmd=start_cmd, address="127.0.0.1", port=8899, sync="tcp:localhost:18899")]
    topology_class = MeshTopology
    topology_params = "num_switches=2"
    patch_panel_class = BufferedPatchPanel
    return SimulationConfig(controllers,
                            topology_class,
                            topology_params,
                            patch_panel_class)

  def test_controller_crash(self):
    simulation = None
    try:
      self.write_controller_crash_superlog()
      simulation_cfg = self.setup_controller_simulation()
      replayer = Replayer(simulation_cfg, self.tmp_controller_superlog)
      simulation = replayer.simulate()
    finally:
      os.unlink(self.tmp_controller_superlog)
      if simulation is not None:
        simulation.clean_up()

  # ------------------------------------------ #
  #        Dataplane Trace Test                #
  # ------------------------------------------ #

  def write_dataplane_trace_superlog(self):
    superlog = open(self.tmp_dataplane_superlog, 'w')
    e1 = str('''{"dependent_labels": [],  "class": "TrafficInjection",'''
             ''' "label": "e1", "time": [0,0], "round": 0}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [],  "class": "TrafficInjection",'''
             ''' "label": "e2", "time": [0,0], "round": 0}''')
    superlog.write(e2 + '\n')
    superlog.close()

  def setup_dataplane_simulation(self):
    controllers = []
    topology_class = MeshTopology
    topology_params = "num_switches=2, ip_format_str='123.123.%d.%d'"
    patch_panel_class = BufferedPatchPanel
    dataplane_trace_path = "./dataplane_traces/ping_pong_same_subnet.trace"
    return SimulationConfig(controllers, topology_class, topology_params,
                            patch_panel_class, dataplane_trace=dataplane_trace_path)

  def test_dataplane_injection(self):
    simulation = None
    try:
      self.write_dataplane_trace_superlog()
      simulation_cfg = self.setup_dataplane_simulation()
      replayer = Replayer(simulation_cfg, self.tmp_dataplane_superlog)
      simulation = replayer.simulate()
    finally:
      os.unlink(self.tmp_dataplane_superlog)
      if simulation is not None:
        simulation.clean_up()

  # ------------------------------------------ #
  #        Host Migration Test                 #
  # ------------------------------------------ #

  def write_migration_superlog(self):
    superlog = open(self.tmp_migration_superlog, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "old_ingress_dpid": 7, "class": "HostMigration",'''
             ''' "old_ingress_port_no": 1, "new_ingress_dpid": 8, '''
             ''' "new_ingress_port_no": 99, "host_id": "host1","label": "e1", "time": [0,0], "round": 0}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "old_ingress_dpid": 8, "class": "HostMigration",'''
             ''' "old_ingress_port_no": 99, "new_ingress_dpid": 7, '''
             ''' "new_ingress_port_no": 101, "host_id": "host1","label": "e2", "time": [0,0], "round": 0}''')
    superlog.write(e2 + '\n')
    superlog.close()

  def setup_migration_simulation(self):
    controllers = []
    topology_class = FatTree
    topology_params = ""
    patch_panel_class = BufferedPatchPanel
    return SimulationConfig(controllers, topology_class, topology_params,
                            patch_panel_class)

  def test_migration(self):
    simulation = None
    try:
      self.write_migration_superlog()
      simulation_cfg = self.setup_migration_simulation()
      replayer = Replayer(simulation_cfg, self.tmp_migration_superlog)
      simulation = replayer.simulate()
      latest_switch = simulation.topology.get_switch(7)
      latest_port = latest_switch.ports[101]
      (host, interface) = simulation.topology.get_connected_port(latest_switch,
                                                                 latest_port)
      self.assertTrue(type(host) == Host)
    finally:
      os.unlink(self.tmp_migration_superlog)
      if simulation is not None:
        simulation.clean_up()

if __name__ == '__main__':
  unittest.main()
