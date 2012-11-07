#!/usr/bin/env python
'''
This file creates the main application window in a separate thread and
invokes the topology widget.
'''

from sts.gui.topology import TopoWidget

import struct
import sys
import getopt
import os
import logging
from threading import Thread
from PyQt4 import QtGui, QtCore

log = logging.getLogger("sts.gui")

class STSGui(object):
    
    def __init__(self, sts_topology):
        self.app = None
        self.mainWindow = None
        self.sts_topology = sts_topology
        gui_thread = Thread(target=self.launchGui)
        gui_thread.start()

    def launchGui(self):
        log.debug("Launching Gui!")
        self.app = QtGui.QApplication(sys.argv)
        self.app.setWindowIcon(QtGui.QIcon('sts/gui/icons/logo.ico'))
        self.mainWindow = MainWindow(self.sts_topology)
        self.mainWindow.show()
        self.app.exec_()

class MainWindow(QtGui.QMainWindow):

    def __init__(self, sts_topology, parent=None):
        QtGui.QWidget.__init__(self, parent)
        
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
        
        self.setCentralWidget(TopoWidget(sts_topology, self))

    def center(self):
        screen = QtGui.QDesktopWidget().screenGeometry()
        size =  self.geometry()
        self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
