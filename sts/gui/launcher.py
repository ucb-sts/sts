'''
This file creates the GUI application window in a separate thread
'''
from sts.gui.view import TopologyView

import struct
import sys
import getopt
import os
import logging
from threading import Thread
from PyQt4 import QtGui, QtCore

log = logging.getLogger("sts.gui")

class GuiLauncher:
  '''
  Invoked directly by the STS Topology class to launch a new GUI instance
  '''
  def __init__(self, sts_topology, syncPeriod=2.0, debugging=False):
    self.app = None
    self.mainWindow = None
    self.sts_topology = sts_topology
    self.syncPeriod = syncPeriod
    self.debugging = debugging
    Thread(target=self.launch).start()

  def launch(self):
    log.debug("Launching Gui!")
    self.app = QtGui.QApplication(sys.argv)
    self.app.setWindowIcon(QtGui.QIcon('sts/gui/icons/logo.ico'))
    self.window = GuiWindow(self.sts_topology, self.syncPeriod, self.debugging)
    self.window.show()
    self.app.exec_()

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
    
    exit = QtGui.QAction('Exit', self)
    exit.setShortcut('Ctrl+Q')
    exit.setStatusTip('Exit application')
    self.connect(exit, QtCore.SIGNAL('triggered()'), QtCore.SLOT('close()'))
    toolbar = self.addToolBar('Exit')
    toolbar.addAction(exit)
    
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
    