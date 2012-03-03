
from pox.openflow.libopenflow_01 import *
from debugger_entities import *

import xml.etree.ElementTree as ET
import os
import glob
import logging

log = logging.getLogger("invariant_checker")

class InvariantChecker():
  def __init__(self, topology):
    self.topology = topology

  # --------------------------------------------------------------#
  #                    Invariant checks                           #
  # --------------------------------------------------------------#
  def check_loops(self):
    pass

  def check_blackholes(self):
    pass

  def check_connectivity(self):
    pass

  def check_routing_consistency(self):
    pass
  
  def check_correspondence(self):
    pass