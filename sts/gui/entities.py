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
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(QtCore.Qt.darkGray).light(25))
    painter.drawRect(-9, -9, 15, 15)
    gradient = QtGui.QRadialGradient(-3, -3, 10)
    color = QtGui.QColor(QtCore.Qt.yellow)
    if option.state & QtGui.QStyle.State_Sunken:
      gradient.setCenter(3, 3)
      gradient.setFocalPoint(3, 3)
      gradient.setColorAt(1, color.light(100))
      gradient.setColorAt(0, color.light(30))
    else:
      gradient.setColorAt(0, color.light(85))
      gradient.setColorAt(1, color.light(25))
    painter.setBrush(QtGui.QBrush(gradient))
    painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
    painter.drawRect(-10, -10, 15, 15)
    # Draw hid
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
    self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)

class GuiSwitch(GuiNode):
  '''
  Interactive Switch
  '''
  def paint(self, painter, option, widget):
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(QtCore.Qt.darkGray).light(25))
    painter.drawEllipse(-9, -9, 20, 20)
    gradient = QtGui.QRadialGradient(-3, -3, 10)
    color = QtGui.QColor(QtCore.Qt.green)
    if option.state & QtGui.QStyle.State_Sunken:
      gradient.setCenter(3, 3)
      gradient.setFocalPoint(3, 3)
      gradient.setColorAt(1, color.light(100))
      gradient.setColorAt(0, color.light(30))
    else:
      gradient.setColorAt(0, color.light(85))
      gradient.setColorAt(1, color.light(25))
    painter.setBrush(QtGui.QBrush(gradient))
    painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
    painter.drawEllipse(-10, -10, 20, 20)
    # Draw dpid
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
    '''
    Popup menu contains:
      Add Link To --
      Remove Link To --
      Attach Host
      Remove Host --
      Remove Switch
    '''
    if event.button() == QtCore.Qt.RightButton:
      popup = QtGui.QMenu()

      # Hack against python scoping
      def create_network_link_lambda(from_dpid, to_dpid):
        return lambda: self.graphics_scene.syncer.create_network_link(from_dpid, to_dpid)
      def remove_network_link_lambda(from_dpid, to_dpid):
        return lambda: self.graphics_scene.syncer.remove_network_link(from_dpid, to_dpid)
      def attach_host_lambda(dpid):
        return lambda: self.graphics_scene.syncer.attach_host_to_switch(dpid)
      def remove_host_lambda(hid):
        return lambda: self.graphics_scene.syncer.remove_host(hid)
      def remove_switch_lambda(dpid):
        return lambda: self.graphics_scene.syncer.remove_switch(dpid)

      addLinkMenu = QtGui.QMenu("Add Link To")
      removeLinkMenu = QtGui.QMenu("Remove Link To")
      removeHostMenu = QtGui.QMenu("Remove Host")

      # Find network links to potentially create
      dpids_to_add = []
      for dpid in self.graphics_scene.syncer.dpid2switch.keys():
        switch = self.graphics_scene.syncer.dpid2switch[dpid]
        if switch is self:
          continue
        for link in self.linkList:
          if link.dest is switch:
            break
        else:
          dpids_to_add.append(switch.id)
      for dpid in sorted(dpids_to_add):
        addLinkMenu.addAction(str(dpid), create_network_link_lambda(self.id, dpid))
      if len(dpids_to_add) > 0:
        popup.addMenu(addLinkMenu)
      
      # Find network links to potentially remove
      dpids_to_remove = []
      for link in self.linkList:
        if isinstance(link.dest, GuiSwitch) and link.dest is not self:
          dpids_to_remove.append(link.dest.id)
      for dpid in sorted(dpids_to_remove):
        removeLinkMenu.addAction(str(dpid), remove_network_link_lambda(self.id, dpid))
      if len(dpids_to_remove) > 0:
        popup.addMenu(removeLinkMenu)
      
      # Attach a host to the given switch
      popup.addAction("Attach Host", attach_host_lambda(self.id))
      
      # Find hosts to potentially remove
      hids_to_remove = []
      for link in self.linkList:
        if isinstance(link.source, GuiHost) and link.dest is self:
          hids_to_remove.append(link.source.id)
      for hid in hids_to_remove:
        removeHostMenu.addAction(str(hid), remove_host_lambda(hid))
      if len(hids_to_remove) > 0:
        popup.addMenu(removeHostMenu)
      
      # Remove self  
      popup.addAction("Remove Switch", remove_switch_lambda(self.id))
          
      popup.exec_(event.lastScreenPos())
      self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)

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
    self.draw_arrow = True
    self.source.addLink(self)
    self.dest.addLink(self)
    self.adjust()

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
    rect = QtCore.QRectF(self.source_point,
               QtCore.QSizeF(self.dest_point.x() - self.source_point.x(),
                       self.dest_point.y() - self.source_point.y())).normalized()
    return rect.adjusted(-extra, -extra, extra, extra)

  def paint(self, painter, option, widget):
    if not self.source or not self.dest:
      return
    line = QtCore.QLineF(self.source_point, self.dest_point)
    if line.length() == 0.0:
      return
    color = QtCore.Qt.gray
    pattern = QtCore.Qt.SolidLine

    # Highlight when clicked/held
    if option.state & QtGui.QStyle.State_Sunken:
      color = QtGui.QColor(color).light(256)
    else:
      color = QtGui.QColor(color).light(90)
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
