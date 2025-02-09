import weakref

from ...backend import QtCore
from ...backend.QtCore import Qt
from ...backend.QtGui import QAction
from ...backend.QtWidgets import QGraphicsScene, QMenu
from .. import ptime
from ..Point import Point
from .mouseEvents import HoverEvent, MouseClickEvent, MouseDragEvent


if hasattr(QtCore, 'PYQT_VERSION'):
    try:
        import sip
        HAVE_SIP = True
    except ImportError:
        HAVE_SIP = False
else:
    HAVE_SIP = False


__all__ = ['GraphicsScene']


class GraphicsScene(QGraphicsScene):
    """Extension of QGraphicsScene that implements a complete, parallel mouse event system.

    (It would have been preferred to just alter the way QGraphicsScene creates and delivers 
    events, but this turned out to be impossible because the constructor for QGraphicsMouseEvent
    is private)
    
    *  Generates MouseClicked events in addition to the usual press/move/release events. 
       (This works around a problem where it is impossible to have one item respond to a 
       drag if another is watching for a click.)
    *  Adjustable radius around click that will catch objects so you don't have to click *exactly* over small/thin objects
    *  Global context menu--if an item implements a context menu, then its parent(s) may also add items to the menu.
    *  Allows items to decide _before_ a mouse click which item will be the recipient of mouse events.
       This lets us indicate unambiguously to the user which item they are about to click/drag on
    *  Eats mouseMove events that occur too soon after a mouse press.
    *  Reimplements items() and itemAt() to circumvent PyQt bug
    
    Mouse interaction is as follows:
    
    1) Every time the mouse moves, the scene delivers both the standard hoverEnter/Move/LeaveEvents 
       as well as custom HoverEvents. 
    2) Items are sent HoverEvents in Z-order and each item may optionally call event.acceptClicks(button), 
       acceptDrags(button) or both. If this method call returns True, this informs the item that _if_ 
       the user clicks/drags the specified mouse button, the item is guaranteed to be the 
       recipient of click/drag events (the item may wish to change its appearance to indicate this).
       If the call to acceptClicks/Drags returns False, then the item is guaranteed to *not* receive
       the requested event (because another item has already accepted it). 
    3) If the mouse is clicked, a mousePressEvent is generated as usual. If any items accept this press event, then
       No click/drag events will be generated and mouse interaction proceeds as defined by Qt. This allows
       items to function properly if they are expecting the usual press/move/release sequence of events.
       (It is recommended that items do NOT accept press events, and instead use click/drag events)
       Note: The default implementation of QGraphicsItem.mousePressEvent will *accept* the event if the 
       item is has its Selectable or Movable flags enabled. You may need to override this behavior.
    4) If no item accepts the mousePressEvent, then the scene will begin delivering mouseDrag and/or mouseClick events.
       If the mouse is moved a sufficient distance (or moved slowly enough) before the button is released, 
       then a mouseDragEvent is generated.
       If no drag events are generated before the button is released, then a mouseClickEvent is generated. 
    5) Click/drag events are delivered to the item that called acceptClicks/acceptDrags on the HoverEvent
       in step 1. If no such items exist, then the scene attempts to deliver the events to items near the event. 
       ClickEvents may be delivered in this way even if no
       item originally claimed it could accept the click. DragEvents may only be delivered this way if it is the initial
       move in a drag.
    """
    # Emitted a list of objects under the cursor when the mouse is
    # moved over the scene.
    mouse_hover_sgn = QtCore.Signal(object)
    # Emitted when the mouse cursor moves over the scene. The position
    # is given in the scene coordinate system.
    mouse_moved_sgn = QtCore.Signal(object)
    # Emitted when the mouse is clicked over the scene. Use ev.pos() to
    # get the click position relative to the item that was clicked on,
    # or ev.scenePos() to get the click position in scene coordinates.
    # See :class:`pyqtgraph.GraphicsScene.MouseClickEvent`.
    mouse_clicked_sgn = QtCore.Signal(object)

    # emitted immediately before the scene is about to be rendered
    prepare_for_paint_sgn = QtCore.Signal()

    def __init__(self, clickRadius=2, moveDistance=5, parent=None):
        super().__init__(parent)
        self.setClickRadius(clickRadius)
        self.setMoveDistance(moveDistance)

        self.clickEvents = []
        self.dragButtons = []
        self.mouseGrabber = None
        self.dragItem = None
        self.lastDrag = None
        self.hoverItems = weakref.WeakKeyDictionary()
        self.lastHoverEvent = None
        self.minDragTime = 0.5  # drags shorter than 0.5 sec are interpreted as clicks
        
        self.contextMenu = []

    def render(self, *args):
        self.prepareForPaint()
        return QGraphicsScene.render(self, *args)

    def prepareForPaint(self):
        """Called before every render.

        This method will inform items that the scene is about to
        be rendered by emitting prepare_for_paint_sgn.
        
        This allows items to delay expensive processing until they know a paint will be required."""
        self.prepare_for_paint_sgn.emit()

    def setClickRadius(self, r):
        """
        Set the distance away from mouse clicks to search for interacting items.
        When clicking, the scene searches first for items that directly intersect the click position
        followed by any other items that are within a rectangle that extends r pixels away from the 
        click position. 
        """
        self._clickRadius = r
        
    def setMoveDistance(self, d):
        """
        Set the distance the mouse must move after a press before mouseMoveEvents will be delivered.
        This ensures that clicks with a small amount of movement are recognized as clicks instead of
        drags.
        """
        self._moveDistance = d

    def mousePressEvent(self, ev):
        QGraphicsScene.mousePressEvent(self, ev)
        if self.mouseGrabberItem() is None:  # nobody claimed press; we are free to generate drag/click events
            if self.lastHoverEvent is not None:
                # If the mouse has moved since the last hover event, send a new one.
                # This can happen if a context menu is open while the mouse is moving.
                if ev.scenePos() != self.lastHoverEvent.scenePos():
                    self.sendHoverEvents(ev)
            
            self.clickEvents.append(MouseClickEvent(ev))
            
            # set focus on the topmost focusable item under this click
            items = self.items(ev.scenePos())
            for i in items:
                if i.isEnabled() and i.isVisible() and (i.flags() & i.GraphicsItemFlag.ItemIsFocusable):
                    i.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                    break
        
    def mouseMoveEvent(self, ev):
        self.mouse_moved_sgn.emit(ev.scenePos())
        
        # First allow QGraphicsScene to deliver hoverEnter/Move/ExitEvents
        QGraphicsScene.mouseMoveEvent(self, ev)
        
        # Next deliver our own HoverEvents
        self.sendHoverEvents(ev)
        
        if ev.buttons():  # button is pressed; send mouseMoveEvents and mouseDragEvents
            QGraphicsScene.mouseMoveEvent(self, ev)
            if self.mouseGrabberItem() is None:
                now = ptime.time()
                init = False
                # keep track of which buttons are involved in dragging
                for btn in [QtCore.Qt.MouseButton.LeftButton,
                            QtCore.Qt.MouseButton.MiddleButton,
                            QtCore.Qt.MouseButton.RightButton]:
                    if not (ev.buttons() & btn):
                        continue
                    if btn not in self.dragButtons:  # see if we've dragged far enough yet
                        cev = [e for e in self.clickEvents if e.button() == btn]
                        if cev:
                            cev = cev[0]
                            dist = Point(ev.scenePos() - cev.scenePos()).length()
                            if dist == 0 or (dist < self._moveDistance and now - cev.time() < self.minDragTime):
                                continue
                            init = init or (len(self.dragButtons) == 0)  # If this is the first button to be dragged, then init=True
                            self.dragButtons.append(btn)
                        
                # If we have dragged buttons, deliver a drag event
                if len(self.dragButtons) > 0:
                    if self.sendDragEvent(ev, init=init):
                        ev.accept()

    def leaveEvent(self, ev):  # inform items that mouse is gone
        if len(self.dragButtons) == 0:
            self.sendHoverEvents(ev, exitOnly=True)
                
    def mouseReleaseEvent(self, ev):
        if self.mouseGrabberItem() is None:
            if ev.button() in self.dragButtons:
                if self.sendDragEvent(ev, final=True):
                    ev.accept()
                self.dragButtons.remove(ev.button())
            else:
                cev = [e for e in self.clickEvents if e.button() == ev.button()]
                if cev:
                    if self.sendClickEvent(cev[0]):
                        ev.accept()
                    self.clickEvents.remove(cev[0])

        if not ev.buttons():
            self.dragItem = None
            self.dragButtons = []
            self.clickEvents = []
            self.lastDrag = None
        QGraphicsScene.mouseReleaseEvent(self, ev)
        
        self.sendHoverEvents(ev)  # let items prepare for next click/drag

    def mouseDoubleClickEvent(self, ev):
        QGraphicsScene.mouseDoubleClickEvent(self, ev)
        if self.mouseGrabberItem() is None:  # nobody claimed press; we are free to generate drag/click events
            self.clickEvents.append(MouseClickEvent(ev, double=True))
        
    def sendHoverEvents(self, ev, exitOnly=False):
        # if exitOnly, then just inform all previously hovered items that the mouse has left.
        
        if exitOnly:
            acceptable=False
            items = []
            event = HoverEvent(None, acceptable)
        else:
            acceptable = not ev.buttons()  # if we are in mid-drag, do not allow items to accept the hover event.
            event = HoverEvent(ev, acceptable)
            items = self.itemsNearEvent(event, hoverable=True)
            self.mouse_hover_sgn.emit(items)
            
        prevItems = list(self.hoverItems.keys())
            
        for item in items:
            if hasattr(item, 'hoverEvent'):
                event.currentItem = item
                if item not in self.hoverItems:
                    self.hoverItems[item] = None
                    event.enter = True
                else:
                    prevItems.remove(item)
                    event.enter = False
                    
                item.hoverEvent(event)
        
        event.enter = False
        event.exit = True
        for item in prevItems:
            event.currentItem = item

            if item.scene() is self:
                item.hoverEvent(event)
            del self.hoverItems[item]
        
        # Update last hover event unless:
        #   - mouse is dragging (move+buttons); in this case we want the dragged
        #     item to continue receiving events until the drag is over
        #   - event is not a mouse event (QEvent.Leave sometimes appears here)
        if (ev.type() == ev.Type.GraphicsSceneMousePress or
            (ev.type() == ev.Type.GraphicsSceneMouseMove and not ev.buttons())):
            self.lastHoverEvent = event  # save this so we can ask about accepted events later.

    def sendDragEvent(self, ev, init=False, final=False):
        # Send a MouseDragEvent to the current dragItem or to
        # items near the beginning of the drag
        event = MouseDragEvent(ev, self.clickEvents[0], self.lastDrag, start=init, finish=final)
        if init and self.dragItem is None:
            if self.lastHoverEvent is not None:
                acceptedItem = self.lastHoverEvent.dragItems().get(event.button(), None)
            else:
                acceptedItem = None
                
            if acceptedItem is not None and acceptedItem.scene() is self:
                self.dragItem = acceptedItem
                event.currentItem = self.dragItem
                try:
                    self.dragItem.mouseDragEvent(event)
                except:
                    print("Error sending drag event:")
                    
            else:
                for item in self.itemsNearEvent(event):
                    if not item.isVisible() or not item.isEnabled():
                        continue
                    if hasattr(item, 'mouseDragEvent'):
                        event.currentItem = item
                        try:
                            item.mouseDragEvent(event)
                        except:
                            print("Error sending drag event:")
                        if event.isAccepted():
                            self.dragItem = item
                            if item.flags() & item.GraphicsItemFlag.ItemIsFocusable:
                                item.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                            break
        elif self.dragItem is not None:
            event.currentItem = self.dragItem
            self.dragItem.mouseDragEvent(event)

        self.lastDrag = event
        
        return event.isAccepted()

    def sendClickEvent(self, ev):
        # if we are in mid-drag, click events may only go to the dragged item.
        if self.dragItem is not None and hasattr(self.dragItem, 'MouseDragEvent'):
            ev.currentItem = self.dragItem
            self.dragItem.mouseClickEvent(ev)
            
        # otherwise, search near the cursor
        else:
            if self.lastHoverEvent is not None:
                acceptedItem = self.lastHoverEvent.clickItems().get(ev.button(), None)
            else:
                acceptedItem = None
            if acceptedItem is not None:
                ev.currentItem = acceptedItem
                acceptedItem.mouseClickEvent(ev)
            else:
                for item in self.itemsNearEvent(ev):
                    if not item.isVisible() or not item.isEnabled():
                        continue
                    if hasattr(item, 'mouseClickEvent'):
                        ev.currentItem = item
                        item.mouseClickEvent(ev)
                            
                        if ev.isAccepted():
                            if item.flags() & item.GraphicsItemFlag.ItemIsFocusable:
                                item.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                            break
        self.mouse_clicked_sgn.emit(ev)
        return ev.isAccepted()
        
    def items(self, *args):
        items = QGraphicsScene.items(self, *args)
        return self.translateGraphicsItems(items)
    
    def selectedItems(self, *args):
        items = QGraphicsScene.selectedItems(self, *args)
        return self.translateGraphicsItems(items)

    def itemAt(self, *args):
        item = QGraphicsScene.itemAt(self, *args)
        return self.translateGraphicsItem(item)

    def itemsNearEvent(self,
                       event,
                       selMode=Qt.ItemSelectionMode.IntersectsItemShape,
                       sortOrder=Qt.SortOrder.DescendingOrder,
                       hoverable=False):
        """
        Return an iterator that iterates first through the items that directly intersect point (in Z order)
        followed by any other items that are within the scene's click radius.
        """
        view = self.views()[0]
        tr = view.viewportTransform()
        r = self._clickRadius
        rect = view.mapToScene(QtCore.QRect(0, 0, 2*r, 2*r)).boundingRect()
        
        if hasattr(event, 'buttonDownScenePos'):
            point = event.buttonDownScenePos()
        else:
            point = event.scenePos()

        items = self.items(point, selMode, sortOrder, tr)
        
        # remove items whose shape does not contain point (scene.items() apparently sucks at this)
        items2 = []
        for item in items:
            if hoverable and not hasattr(item, 'hoverEvent'):
                continue
            if item.scene() is not self:
                continue
            shape = item.shape() # Note: default shape() returns boundingRect()
            if shape is None:
                continue
            if shape.contains(item.mapFromScene(point)):
                items2.append(item)
        
        # Sort by descending Z-order (don't trust scene.itms() to do this either)
        # use 'absolute' z value, which is the sum of all item/parent ZValues
        def absZValue(item):
            if item is None:
                return 0
            return item.zValue() + absZValue(item.parentItem())
        
        items2.sort(key=absZValue, reverse=True)
        
        return items2
        
    def getViewWidget(self):
        return self.views()[0]

    def addParentContextMenus(self, item, menu, event):
        """
        Can be called by any item in the scene to expand its context menu to include parent context menus.
        Parents may implement getContextMenus to add new menus / actions to the existing menu.
        getContextMenus must accept 1 argument (the event that generated the original menu) and
        return a single QMenu or a list of QMenus.
        
        The final menu will look like:
        
            |    Original Item 1
            |    Original Item 2
            |    ...
            |    Original Item N
            |    ------------------
            |    Parent Item 1
            |    Parent Item 2
            |    ...
            |    Grandparent Item 1
            |    ...
            
        
        ==============  ==================================================
        **Arguments:**
        item            The item that initially created the context menu 
                        (This is probably the item making the call to this function)
        menu            The context menu being shown by the item
        event           The original event that triggered the menu to appear.
        ==============  ==================================================
        """
        menusToAdd = []
        while item is not self:
            item = item.parentItem()
            if item is None:
                item = self
            if not hasattr(item, "getContextMenus"):
                continue
            subMenus = item.getContextMenus(event) or []
            if isinstance(subMenus, list): # so that some items (like FlowchartViewBox) can return multiple menus
                menusToAdd.extend(subMenus)
            else:
                menusToAdd.append(subMenus)

        if menusToAdd:
            menu.addSeparator()

        for m in menusToAdd:
            if isinstance(m, QMenu):
                menu.addMenu(m)
            elif isinstance(m, QAction):
                menu.addAction(m)
            else:
                raise Exception("Cannot add object %s (type=%s) to QMenu." % (str(m), str(type(m))))
            
        return menu

    def getContextMenus(self, event):
        self.contextMenuItem = event.acceptedItem
        return self.contextMenu

    @staticmethod
    def translateGraphicsItem(item):
        # This function is intended as a workaround for a problem with older
        # versions of PyQt (< 4.9?), where methods returning 'QGraphicsItem *'
        # lose the type of the QGraphicsObject subclasses and instead return
        # generic QGraphicsItem wrappers.
        if HAVE_SIP and isinstance(item, sip.wrapper):
            obj = item.toGraphicsObject()
            if obj is not None:
                item = obj
        return item

    @staticmethod
    def translateGraphicsItems(items):
        return list(map(GraphicsScene.translateGraphicsItem, items))
