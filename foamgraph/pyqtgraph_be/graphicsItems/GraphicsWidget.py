from ...backend.QtGui import QPainterPath
from ...backend.QtWidgets import QGraphicsWidget

from .GraphicsItem import GraphicsItem

__all__ = ['GraphicsWidget']


class GraphicsWidget(GraphicsItem, QGraphicsWidget):
    
    _qtBaseClass = QGraphicsWidget

    def __init__(self, *args, **kargs):
        """
        **Bases:** :class:`GraphicsItem <pyqtgraph.GraphicsItem>`, :class:`QtGui.QGraphicsWidget`
        
        Extends QGraphicsWidget with several helpful methods and workarounds for PyQt bugs. 
        Most of the extra functionality is inherited from :class:`GraphicsItem <pyqtgraph.GraphicsItem>`.
        """
        QGraphicsWidget.__init__(self, *args, **kargs)
        GraphicsItem.__init__(self)

    def setFixedHeight(self, h):
        self.setMaximumHeight(h)
        self.setMinimumHeight(h)

    def setFixedWidth(self, h):
        self.setMaximumWidth(h)
        self.setMinimumWidth(h)
        
    def height(self):
        return self.geometry().height()
    
    def width(self):
        return self.geometry().width()

    def boundingRect(self):
        return self.mapRectFromParent(self.geometry()).normalized()
        
    def shape(self):  # No idea why this is necessary, but rotated items do not receive clicks otherwise.
        p = QPainterPath()
        p.addRect(self.boundingRect())
        return p
