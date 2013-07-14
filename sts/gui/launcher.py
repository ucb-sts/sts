# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
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
This file creates the GUI application window in a separate thread
'''
from sts.gui.view import TopologyView

import sys
import logging
from threading import Thread
from PyQt4 import QtGui, QtCore

log = logging.getLogger("sts.gui")

class TopologyGui:
  '''
  Invoked directly by the STS Topology class to launch a new GUI instance
  '''
  def __init__(self, sts_topology, syncPeriod=2.0, debugging=False):
    self.app = None
    self.mainWindow = None
    self.sts_topology = sts_topology
    self.syncPeriod = syncPeriod
    self.debugging = debugging

  def launch(self):
    def create_gui_instance():
      self.app = QtGui.QApplication(sys.argv)
      self.app.setWindowIcon(QtGui.QIcon('sts/gui/icons/logo.ico'))
      self.window = GuiWindow(self.sts_topology, self.syncPeriod, self.debugging)
      self.window.show()
      self.app.exec_()
    Thread(target=create_gui_instance).start()

class GuiWindow(QtGui.QMainWindow):
  '''
  QMainWindow container for TopologyWidget
  '''
  def __init__(self, sts_topology, syncPeriod=2.0, debugging=False):
    QtGui.QWidget.__init__(self)
    self.setWindowTitle('STS Graphical User Interface')
    self.resize(640, 640)
    self.statusBar().showMessage('Ready')
    self.center()
    QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self.close)
    self.setCentralWidget(TopologyWidget(sts_topology, self, syncPeriod, debugging))

  def center(self):
    screen = QtGui.QDesktopWidget().screenGeometry()
    size = self.geometry()
    self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)

class TopologyWidget(QtGui.QWidget):
  '''
  QWidget container for TopologyView
  '''
  def __init__(self, sts_topology, parent=None, syncPeriod=2.0, debugging=False):
    QtGui.QWidget.__init__(self)
    self.topology_view = TopologyView(sts_topology, self, syncPeriod, debugging)
    vbox = QtGui.QVBoxLayout()
    vbox.addWidget(self.topology_view)
    self.setLayout(vbox)
    self.resize(300, 150)

