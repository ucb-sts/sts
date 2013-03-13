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
Host, switch and link GUI entities that belong to the QGraphicsScene in TopologyView  
'''
import math
from PyQt4 import QtGui, QtCore

class GuiNode(QtGui.QGraphicsItem):
  '''
  Abstract Interactive Node
    If switch, id = switch.dpid
    If host, id = host.hid
  '''
  def __init__(self, graphics_scene, _id):
    QtGui.QGraphicsItem.__init__(self)
    self.graphics_scene = graphics_scene
    self.id = _id
    self.linkList = []
    self.newPos = QtCore.QPointF()
    self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
    self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges)
    self.setZValue(1)
    self.setAcceptHoverEvents(True)
    
    # Node attributes
    self.is_up = True     # up/down state   
    self.showID = True    # Draw node ID
    self.showNode = True  # Draw node

  def addLink(self, link):
    self.linkList.append(link)
    link.adjust()

  def links(self):
    return self.linkList

  def boundingRect(self):
    adjust = 2.0
    return QtCore.QRectF(-10 - adjust, -10 - adjust, 23 + adjust, 23 + adjust)

  def shape(self):
    path = QtGui.QPainterPath()
    path.addEllipse(-10, -10, 20, 20)
    return path
    
  def itemChange(self, change, value):
    if change == QtGui.QGraphicsItem.ItemPositionChange:
      for link in self.linkList:
        link.adjust()
    return QtGui.QGraphicsItem.itemChange(self, change, value)

  def mousePressEvent(self, event):
    self.still_hover = False
    self.update()
    QtGui.QGraphicsItem.mousePressEvent(self, event)

  def mouseDoubleClickEvent(self, event):
    QtGui.QGraphicsItem.mouseDoubleClickEvent(self, event)
  
  @QtCore.pyqtSlot()  
  def popupnode_detailsMenu(self):
    if self.still_hover:
      self.node_details.exec_(self.hover_pos)
    
  def hoverLeaveEvent(self, event):
    self.still_hover = False

class GuiHost(GuiNode):
  '''
  Interactive Host
  '''
  def paint(self, painter, option, widget):
    if self.showNode:
      painter.setPen(QtCore.Qt.NoPen)
      painter.setBrush(QtGui.QColor(QtCore.Qt.darkGray).light(25))
      painter.drawRect(-9, -9, 15, 15)
      gradient = QtGui.QRadialGradient(-3, -3, 10)
      color = QtGui.QColor(QtCore.Qt.yellow)
      if option.state & QtGui.QStyle.State_Sunken:
        gradient.setCenter(3, 3)
        gradient.setFocalPoint(3, 3)
        if self.is_up:
          gradient.setColorAt(1, color.light(100))
          gradient.setColorAt(0, color.light(30))
        else:
          gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(80))
          gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(20))
      else:
        if self.is_up:
          gradient.setColorAt(0, color.light(85))
          gradient.setColorAt(1, color.light(25))
        else:
          gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(60))
          gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(10))
      painter.setBrush(QtGui.QBrush(gradient))
      painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
      painter.drawRect(-10, -10, 15, 15)
      
    if self.showID:
      text_rect = self.boundingRect()
      message = str(self.id)
      font = painter.font()
      font.setBold(True)
      painter.setFont(font)
      painter.setPen(QtCore.Qt.gray)
      painter.drawText(text_rect.translated(0.1, 0.1), message)
      painter.setPen(QtGui.QColor(QtCore.Qt.gray).light(130))
      painter.drawText(text_rect.translated(0, 0), message)
  
  def mouseReleaseEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
      popup = QtGui.QMenu()
      popup.addMenu(self.node_details)
      popup.exec_(event.lastScreenPos())
    self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)
  
  def hoverEnterEvent(self, event):
    self.still_hover = True
    self.node_details = QtGui.QMenu('&Node Details')
    self.node_details.addAction('Host ID: 0x%s' % self.id)
    self.hover_pos = event.lastScreenPos() + QtCore.QPoint(10, 10)
    self.hover_timer = QtCore.QTimer()
    self.hover_timer.singleShot(500, self.popupnode_detailsMenu)
  
class GuiSwitch(GuiNode):
  '''
  Interactive Switch
  '''
  def paint(self, painter, option, widget):
    if self.showNode:
      painter.setPen(QtCore.Qt.NoPen)
      painter.setBrush(QtGui.QColor(QtCore.Qt.darkGray).light(25))
      painter.drawEllipse(-9, -9, 20, 20)
      gradient = QtGui.QRadialGradient(-3, -3, 10)
      color = QtGui.QColor(QtCore.Qt.green)
      if option.state & QtGui.QStyle.State_Sunken:
        gradient.setCenter(3, 3)
        gradient.setFocalPoint(3, 3)
        if self.is_up:
          gradient.setColorAt(1, color.light(100))
          gradient.setColorAt(0, color.light(30))
        else:
          gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(80))
          gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(20))
      else:
        if self.is_up:
          gradient.setColorAt(0, color.light(85))
          gradient.setColorAt(1, color.light(25))
        else:
          gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(60))
          gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(10))
      painter.setBrush(QtGui.QBrush(gradient))
      painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
      painter.drawEllipse(-10, -10, 20, 20)
    
    if self.showID:
      text_rect = self.boundingRect()
      message = str(self.id)
      font = painter.font()
      font.setBold(True)
      painter.setFont(font)
      painter.setPen(QtCore.Qt.gray)
      painter.drawText(text_rect.translated(0.1, 0.1), message)
      painter.setPen(QtGui.QColor(QtCore.Qt.gray).light(130))
      painter.drawText(text_rect.translated(0, 0), message)

  def mouseReleaseEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
      popup = QtGui.QMenu()
      linkToMenu = QtGui.QMenu("Link to")
        
      # Hack against python scoping
      def create_network_link_lambda(from_id, to_id):
        return lambda: self.graphics_scene.syncer.create_network_link(from_id, to_id)
        
      # Creates a link to another unconnected switch
      for dpid in sorted(self.graphics_scene.syncer.dpid2switch.keys()):
        switch = self.graphics_scene.syncer.dpid2switch[dpid]
        if switch == self:
          continue
        for link in self.linkList:
          if (link.source == switch or link.dest == switch):
            break
        else:
          linkToMenu.addAction(str(switch.id), create_network_link_lambda(self.id, switch.id))
      popup.addMenu(linkToMenu)
      popup.exec_(event.lastScreenPos())
      self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)

  def hoverEnterEvent(self, event):
    self.still_hover = True
    self.node_details = QtGui.QMenu('&Node Details')
    self.node_details.addAction('Datapath ID: 0x%s' % self.id)
    self.hover_pos = event.lastScreenPos() + QtCore.QPoint(10, 10)
    self.hover_timer = QtCore.QTimer()
    self.hover_timer.singleShot(500, self.popupnode_detailsMenu)
    
class GuiLink(QtGui.QGraphicsItem):
  '''
  Interactive Link 
  '''
  def __init__(self, graphics_scene, source_node, dest_node):
    QtGui.QGraphicsItem.__init__(self)
    self.graphics_scene = graphics_scene
    self.arrow_size = 10.0
    self.source_point = QtCore.QPointF()
    self.dest_point = QtCore.QPointF()
    self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
    self.setAcceptedMouseButtons(QtCore.Qt.RightButton)
    self.setAcceptHoverEvents(False)
    self.source = source_node
    self.dest = dest_node
    self.draw_arrow = False
    self.source.addLink(self)
    self.dest.addLink(self)
    self.adjust()
    
    # Link attributes
    self.is_up = True    # up/down state  
    self.show_link = True  # Draw link
    self.show_id = False   # Draw link ID   
    self.show_ports = True   # Draw connecting ports  
    
  def adjust(self):
    if not self.source or not self.dest:
      return
    line = QtCore.QLineF(self.mapFromItem(self.source, 0, 0), \
                self.mapFromItem(self.dest, 0, 0))
    length = line.length()
    if length == 0.0:
      return
    linkOffset = QtCore.QPointF((line.dx() * 10) / length, (line.dy() * 10) / length)

    self.prepareGeometryChange()
    self.source_point = line.p1() + linkOffset
    self.dest_point = line.p2() - linkOffset

  def boundingRect(self):
    if not self.source or not self.dest:
      return QtCore.QRectF()
    penWidth = 1
    extra = (penWidth + self.arrow_size) / 2.0
    return QtCore.QRectF(self.source_point,
               QtCore.QSizeF(self.dest_point.x() - self.source_point.x(),
                       self.dest_point.y() - self.source_point.y())).normalized().adjusted(-extra, -extra, extra, extra)
    
  def paint(self, painter, option, widget):
    if not self.source or not self.dest:
      return

    # Draw the line itself.
    if self.show_link:
      line = QtCore.QLineF(self.source_point, self.dest_point)
      if line.length() == 0.0:
        return
      
      color = QtCore.Qt.gray
      pattern = QtCore.Qt.SolidLine
      
      # Select pen for line (color for util, pattern for state)
      if self.is_up:
        # Highlight when clicked/held
        if option.state & QtGui.QStyle.State_Sunken:
          color = QtGui.QColor(color).light(256)
        else:
          color = QtGui.QColor(color).light(90)
      else:
        color = QtCore.Qt.darkGray
        pattern = QtCore.Qt.DashLine
              
      painter.setPen(QtGui.QPen(color, 1,
        pattern, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
      painter.drawLine(line)
    
      # Draw the arrows if there's enough room.
      angle = math.acos(line.dx() / line.length())
      if line.dy() >= 0:
        angle = 2 * math.pi - angle

      dest_arrow_p1 = self.dest_point + \
        QtCore.QPointF(math.sin(angle - math.pi / 3) * self.arrow_size,
        math.cos(angle - math.pi / 3) * self.arrow_size)
      dest_arrow_p2 = self.dest_point + \
        QtCore.QPointF(math.sin(angle - math.pi + math.pi / 3) * self.arrow_size,
        math.cos(angle - math.pi + math.pi / 3) * self.arrow_size)
      
      if self.draw_arrow:
        painter.setBrush(color)
        painter.drawPolygon(QtGui.QPolygonF([line.p2(), \
          dest_arrow_p1, dest_arrow_p2]))
    
  def mouseReleaseEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
      popup = QtGui.QMenu()
      popup.addMenu(self.link_details)
      popup.exec_(event.lastScreenPos())
    self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)
