import itertools
from functools import reduce

from ..Qt import QtGui, QtCore, isQObjectAlive
from ..GraphicsScene import GraphicsScene
from ..Point import Point
from .. import functions as fn
import weakref
import operator


class LRUCache(object):
    '''
    This LRU cache should be reasonable for short collections (until around 100 items), as it does a
    sort on the items if the collection would become too big (so, it is very fast for getting and
    setting but when its size would become higher than the max size it does one sort based on the
    internal time to decide which items should be removed -- which should be Ok if the resizeTo
    isn't too close to the maxSize so that it becomes an operation that doesn't happen all the
    time).
    '''

    def __init__(self, maxSize=100, resizeTo=70):
        '''
        ============== =========================================================
        **Arguments:**
        maxSize        (int) This is the maximum size of the cache. When some
                       item is added and the cache would become bigger than
                       this, it's resized to the value passed on resizeTo.
        resizeTo       (int) When a resize operation happens, this is the size
                       of the final cache.
        ============== =========================================================
        '''
        assert resizeTo < maxSize
        self.maxSize = maxSize
        self.resizeTo = resizeTo
        self._counter = 0
        self._dict = {}
        self._nextTime = itertools.count(0).__next__

    def __getitem__(self, key):
        item = self._dict[key]
        item[2] = self._nextTime()
        return item[1]

    def __len__(self):
        return len(self._dict)

    def __setitem__(self, key, value):
        item = self._dict.get(key)
        if item is None:
            if len(self._dict) + 1 > self.maxSize:
                self._resizeTo()

            item = [key, value, self._nextTime()]
            self._dict[key] = item
        else:
            item[1] = value
            item[2] = self._nextTime()

    def __delitem__(self, key):
        del self._dict[key]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def clear(self):
        self._dict.clear()

    def values(self):
        return [i[1] for i in self._dict.values()]

    def keys(self):
        return [x[0] for x in self._dict.values()]

    def _resizeTo(self):
        ordered = sorted(self._dict.values(), key=operator.itemgetter(2))[:self.resizeTo]
        for i in ordered:
            del self._dict[i[0]]

    def items(self, accessTime=False):
        '''
        :param bool accessTime:
            If True sorts the returned items by the internal access time.
        '''
        if accessTime:
            for x in sorted(self._dict.values(), key=operator.itemgetter(2)):
                yield x[0], x[1]
        else:
            for x in self._dict.items():
                yield x[0], x[1]


class GraphicsItem(object):
    """
    **Bases:** :class:`object`

    Abstract class providing useful methods to GraphicsObject and GraphicsWidget.
    (This is required because we cannot have multiple inheritance with QObject subclasses.)

    A note about Qt's GraphicsView framework:

    The GraphicsView system places a lot of emphasis on the notion that the graphics within
    the scene should be device independent--you should be able to take the same graphics and
    display them on screens of different resolutions, printers, export to SVG, etc.

    This is nice in principle, but causes me a lot of headache in practice. It means that
    I have to circumvent all the device-independent expectations any time I want to operate
    in pixel coordinates rather than arbitrary scene coordinates.

    A lot of the code in GraphicsItem is devoted to this task--keeping track of view widgets
    and device transforms, computing the size and shape of a pixel in local item coordinates,
    etc. Note that in item coordinates, a pixel does not have to be square or even rectangular,
    so just asking how to increase a bounding rect by 2px can be a rather complex task.
    """
    _pixelVectorGlobalCache = LRUCache(100, 70)
    _mapRectFromViewGlobalCache = LRUCache(100, 70)

    def __init__(self):
        if not hasattr(self, '_qtBaseClass'):
            for b in self.__class__.__bases__:
                if issubclass(b, QtGui.QGraphicsItem):
                    self.__class__._qtBaseClass = b
                    break
        if not hasattr(self, '_qtBaseClass'):
            raise Exception('Could not determine Qt base class for GraphicsItem: %s' % str(self))

        self._pixelVectorCache = [None, None]
        self._viewWidget = None
        self._viewBox = None
        self._connectedView = None
        self._exportOpts = False   ## If False, not currently exporting. Otherwise, contains dict of export options.
        self._cachedView = None

    def getViewWidget(self):
        """
        Return the view widget for this item. 
        
        If the scene has multiple views, only the first view is returned.
        The return value is cached; clear the cached value with forgetViewWidget().
        If the view has been deleted by Qt, return None.
        """
        if self._viewWidget is None:
            scene = self.scene()
            if scene is None:
                return None
            views = scene.views()
            if len(views) < 1:
                return None
            self._viewWidget = weakref.ref(self.scene().views()[0])
            
        v = self._viewWidget()
        if v is not None and not isQObjectAlive(v):
            return None
            
        return v
    
    def forgetViewWidget(self):
        self._viewWidget = None
    
    def getViewBox(self):
        """
        Return the first ViewBox or GraphicsView which bounds this item's visible space.
        If this item is not contained within a ViewBox, then the GraphicsView is returned.
        If the item is contained inside nested ViewBoxes, then the inner-most ViewBox is returned.
        The result is cached; clear the cache with forgetViewBox()
        """
        if self._viewBox is None:
            p = self
            while True:
                try:
                    p = p.parentItem()
                except RuntimeError:  ## sometimes happens as items are being removed from a scene and collected.
                    return None
                if p is None:
                    vb = self.getViewWidget()
                    if vb is None:
                        return None
                    else:
                        self._viewBox = weakref.ref(vb)
                        break
                if hasattr(p, 'implements') and p.implements('ViewBox'):
                    self._viewBox = weakref.ref(p)
                    break
        return self._viewBox()  ## If we made it this far, _viewBox is definitely not None

    def forgetViewBox(self):
        self._viewBox = None
        
    def deviceTransform(self, viewportTransform=None):
        """
        Return the transform that converts local item coordinates to device coordinates (usually pixels).
        Extends deviceTransform to automatically determine the viewportTransform.
        """
        if self._exportOpts is not False and 'painter' in self._exportOpts: ## currently exporting; device transform may be different.
            scaler = self._exportOpts.get('resolutionScale', 1.0)
            return self.sceneTransform() * QtGui.QTransform(scaler, 0, 0, scaler, 1, 1)

        if viewportTransform is None:
            view = self.getViewWidget()
            if view is None:
                return None
            viewportTransform = view.viewportTransform()
        dt = self._qtBaseClass.deviceTransform(self, viewportTransform)

        if dt.determinant() == 0:  ## occurs when deviceTransform is invalid because widget has not been displayed
            return None
        else:
            return dt
        
    def viewTransform(self):
        """Return the transform that maps from local coordinates to the item's ViewBox coordinates
        If there is no ViewBox, return the scene transform.
        Returns None if the item does not have a view."""
        view = self.getViewBox()
        if view is None:
            return None
        if hasattr(view, 'implements') and view.implements('ViewBox'):
            tr = self.itemTransform(view.innerSceneItem())
            if isinstance(tr, tuple):
                tr = tr[0]   ## difference between pyside and pyqt
            return tr
        else:
            return self.sceneTransform()

    def getBoundingParents(self):
        """Return a list of parents to this item that have child clipping enabled."""
        p = self
        parents = []
        while True:
            p = p.parentItem()
            if p is None:
                break
            if p.flags() & self.GraphicsItemFlag.ItemClipsChildrenToShape:
                parents.append(p)
        return parents
    
    def viewRect(self):
        """Return the visible bounds of this item's ViewBox or GraphicsWidget,
        in the local coordinate system of the item."""
        view = self.getViewBox()
        if view is None:
            return None
        bounds = self.mapRectFromView(view.viewRect())
        if bounds is None:
            return None

        return bounds.normalized()

    def pixelVectors(self, direction=None):
        """Return vectors in local coordinates representing the width and height of a view pixel.
        If direction is specified, then return vectors parallel and orthogonal to it.
        
        Return (None, None) if pixel size is not yet defined (usually because the item has not yet been displayed)
        or if pixel size is below floating-point precision limit.
        """
        
        ## This is an expensive function that gets called very frequently.
        ## We have two levels of cache to try speeding things up.
        
        dt = self.deviceTransform()
        if dt is None:
            return None, None
            
        ## Ignore translation. If the translation is much larger than the scale
        ## (such as when looking at unix timestamps), we can get floating-point errors.
        dt.setMatrix(dt.m11(), dt.m12(), 0, dt.m21(), dt.m22(), 0, 0, 0, 1)
        
        if direction is None:
            direction = QtCore.QPointF(1, 0)
        elif direction.manhattanLength() == 0:
            raise Exception("Cannot compute pixel length for 0-length vector.")

        key = (dt.m11(), dt.m21(), dt.m12(), dt.m22(), direction.x(), direction.y())

        ## check local cache
        if key == self._pixelVectorCache[0]:
            return tuple(map(Point, self._pixelVectorCache[1]))  ## return a *copy*

        ## check global cache
        pv = self._pixelVectorGlobalCache.get(key, None)
        if pv is not None:
            self._pixelVectorCache = [key, pv]
            return tuple(map(Point,pv))  ## return a *copy*

        ## attempt to re-scale direction vector to fit within the precision of the coordinate system
        ## Here's the problem: we need to map the vector 'direction' from the item to the device, via transform 'dt'.
        ## In some extreme cases, this mapping can fail unless the length of 'direction' is cleverly chosen.
        ## Example:
        ##   dt = [ 1, 0,    2 
        ##          0, 2, 1e20
        ##          0, 0,    1 ]
        ## Then we map the origin (0,0) and direction (0,1) and get:
        ##    o' = 2,1e20
        ##    d' = 2,1e20  <-- should be 1e20+2, but this can't be represented with a 32-bit float
        ##    
        ##    |o' - d'|  == 0    <-- this is the problem.
        
        ## Perhaps the easiest solution is to exclude the transformation column from dt. Does this cause any other problems?
        
        #if direction.x() == 0:
            #r = abs(dt.m32())/(abs(dt.m12()) + abs(dt.m22()))
            ##r = 1.0/(abs(dt.m12()) + abs(dt.m22()))
        #elif direction.y() == 0:
            #r = abs(dt.m31())/(abs(dt.m11()) + abs(dt.m21()))
            ##r = 1.0/(abs(dt.m11()) + abs(dt.m21()))
        #else:
            #r = ((abs(dt.m32())/(abs(dt.m12()) + abs(dt.m22()))) * (abs(dt.m31())/(abs(dt.m11()) + abs(dt.m21()))))**0.5
        #if r == 0:
            #r = 1.  ## shouldn't need to do this; probably means the math above is wrong?
        #directionr = direction * r
        directionr = direction
        
        ## map direction vector onto device
        #viewDir = Point(dt.map(directionr) - dt.map(Point(0,0)))
        #mdirection = dt.map(directionr)
        dirLine = QtCore.QLineF(QtCore.QPointF(0,0), directionr)
        viewDir = dt.map(dirLine)
        if viewDir.length() == 0:
            return None, None   ##  pixel size cannot be represented on this scale
           
        ## get unit vector and orthogonal vector (length of pixel)
        #orthoDir = Point(viewDir[1], -viewDir[0])  ## orthogonal to line in pixel-space
        try:  
            normView = viewDir.unitVector()
            #normView = viewDir.norm()  ## direction of one pixel orthogonal to line
            normOrtho = normView.normalVector()
            #normOrtho = orthoDir.norm()
        except:
            raise Exception("Invalid direction %s" %directionr)
            
        ## map back to item 
        dti = fn.invertQTransform(dt)
        #pv = Point(dti.map(normView)-dti.map(Point(0,0))), Point(dti.map(normOrtho)-dti.map(Point(0,0)))
        pv = Point(dti.map(normView).p2()), Point(dti.map(normOrtho).p2())
        self._pixelVectorCache[1] = pv
        self._pixelVectorCache[0] = dt
        self._pixelVectorGlobalCache[key] = pv
        return self._pixelVectorCache[1]
        
    def pixelLength(self, direction, ortho=False):
        """Return the length of one pixel in the direction indicated (in local coordinates)
        If ortho=True, then return the length of one pixel orthogonal to the direction indicated.
        
        Return None if pixel size is not yet defined (usually because the item has not yet been displayed).
        """
        normV, orthoV = self.pixelVectors(direction)
        if normV is None or orthoV is None:
            return None
        if ortho:
            return orthoV.length()
        return normV.length()

    def pixelSize(self):
        ## deprecated
        v = self.pixelVectors()
        if v == (None, None):
            return None, None
        return (v[0].x()**2+v[0].y()**2)**0.5, (v[1].x()**2+v[1].y()**2)**0.5

    def pixelWidth(self):
        ## deprecated
        vt = self.deviceTransform()
        if vt is None:
            return 0
        vt = fn.invertQTransform(vt)
        return vt.map(QtCore.QLineF(0, 0, 1, 0)).length()
        
    def pixelHeight(self):
        ## deprecated
        vt = self.deviceTransform()
        if vt is None:
            return 0
        vt = fn.invertQTransform(vt)
        return vt.map(QtCore.QLineF(0, 0, 0, 1)).length()

    def mapToDevice(self, obj):
        """
        Return *obj* mapped from local coordinates to device coordinates (pixels).
        If there is no device mapping available, return None.
        """
        vt = self.deviceTransform()
        if vt is None:
            return None
        return vt.map(obj)
        
    def mapFromDevice(self, obj):
        """
        Return *obj* mapped from device coordinates (pixels) to local coordinates.
        If there is no device mapping available, return None.
        """
        vt = self.deviceTransform()
        if vt is None:
            return None
        if isinstance(obj, QtCore.QPoint):
            obj = QtCore.QPointF(obj)
        vt = fn.invertQTransform(vt)
        return vt.map(obj)

    def mapRectToDevice(self, rect):
        """
        Return *rect* mapped from local coordinates to device coordinates (pixels).
        If there is no device mapping available, return None.
        """
        vt = self.deviceTransform()
        if vt is None:
            return None
        return vt.mapRect(rect)

    def mapRectFromDevice(self, rect):
        """
        Return *rect* mapped from device coordinates (pixels) to local coordinates.
        If there is no device mapping available, return None.
        """
        vt = self.deviceTransform()
        if vt is None:
            return None
        vt = fn.invertQTransform(vt)
        return vt.mapRect(rect)
    
    def mapToView(self, obj):
        vt = self.viewTransform()
        if vt is None:
            return None
        return vt.map(obj)
        
    def mapRectToView(self, obj):
        vt = self.viewTransform()
        if vt is None:
            return None
        return vt.mapRect(obj)
        
    def mapFromView(self, obj):
        vt = self.viewTransform()
        if vt is None:
            return None
        vt = fn.invertQTransform(vt)
        return vt.map(obj)

    def mapRectFromView(self, obj):
        vt = self.viewTransform()
        if vt is None:
            return None

        cache = self._mapRectFromViewGlobalCache
        k = (
            vt.m11(), vt.m12(), vt.m13(),
            vt.m21(), vt.m22(), vt.m23(),
            vt.m31(), vt.m32(), vt.m33(),
        )

        try:
            inv_vt = cache[k]
        except KeyError:
            inv_vt = fn.invertQTransform(vt)
            cache[k] = inv_vt

        return inv_vt.mapRect(obj)

    def pos(self):
        return Point(self._qtBaseClass.pos(self))
    
    def viewPos(self):
        return self.mapToView(self.mapFromParent(self.pos()))
    
    def parentItem(self):
        ## PyQt bug -- some items are returned incorrectly.
        return GraphicsScene.translateGraphicsItem(self._qtBaseClass.parentItem(self))
        
    def setParentItem(self, parent):
        ## Workaround for Qt bug: https://bugreports.qt-project.org/browse/QTBUG-18616
        if parent is not None:
            pscene = parent.scene()
            if pscene is not None and self.scene() is not pscene:
                pscene.addItem(self)
        return self._qtBaseClass.setParentItem(self, parent)
    
    def childItems(self):
        ## PyQt bug -- some child items are returned incorrectly.
        return list(map(GraphicsScene.translateGraphicsItem, self._qtBaseClass.childItems(self)))

    def sceneTransform(self):
        ## Qt bug: do no allow access to sceneTransform() until 
        ## the item has a scene.
        
        if self.scene() is None:
            return self.transform()
        else:
            return self._qtBaseClass.sceneTransform(self)

    def transformAngle(self, relativeItem=None):
        """Return the rotation produced by this item's transform (this assumes there is no shear in the transform)
        If relativeItem is given, then the angle is determined relative to that item.
        """
        if relativeItem is None:
            relativeItem = self.parentItem()

        tr = self.itemTransform(relativeItem)
        if isinstance(tr, tuple):  ## difference between pyside and pyqt
            tr = tr[0]
        #vec = tr.map(Point(1,0)) - tr.map(Point(0,0))
        vec = tr.map(QtCore.QLineF(0,0,1,0))
        #return Point(vec).angle(Point(1,0))
        return vec.angleTo(QtCore.QLineF(vec.p1(), vec.p1()+QtCore.QPointF(1,0)))

    def parentChanged(self):
        """Called when the item's parent has changed.

        This method handles connecting / disconnecting from ViewBox signals
        to make sure viewRangeChanged works properly. It should generally be 
        extended, not overridden."""
        self._updateView()

    def _updateView(self):
        ## called to see whether this item has a new view to connect to
        ## NOTE: This is called from GraphicsObject.itemChange or GraphicsWidget.itemChange.

        if not hasattr(self, '_connectedView'):
            # Happens when Python is shutting down.
            return

        ## It is possible this item has moved to a different ViewBox or widget;
        ## clear out previously determined references to these.
        self.forgetViewBox()
        self.forgetViewWidget()
        
        ## check for this item's current viewbox or view widget
        view = self.getViewBox()

        oldView = None
        if self._connectedView is not None:
            oldView = self._connectedView()
            
        if view is oldView:
            return

        ## disconnect from previous view
        if oldView is not None:
            for signal, slot in [('sigRangeChanged', self.viewRangeChanged),
                                 ('sigDeviceRangeChanged', self.viewRangeChanged), 
                                 ('sigTransformChanged', self.viewTransformChanged), 
                                 ('sigDeviceTransformChanged', self.viewTransformChanged)]:
                try:
                    getattr(oldView, signal).disconnect(slot)
                except (TypeError, AttributeError, RuntimeError):
                    # TypeError and RuntimeError are from pyqt and pyside, respectively
                    pass
            
            self._connectedView = None

        ## connect to new view
        if view is not None:
            if hasattr(view, 'sigDeviceRangeChanged'):
                # connect signals from GraphicsView
                view.sigDeviceRangeChanged.connect(self.viewRangeChanged)
                view.sigDeviceTransformChanged.connect(self.viewTransformChanged)
            else:
                # connect signals from ViewBox
                view.sigRangeChanged.connect(self.viewRangeChanged)
                view.sigTransformChanged.connect(self.viewTransformChanged)
            self._connectedView = weakref.ref(view)
            self.viewRangeChanged()
            self.viewTransformChanged()
        
        ## inform children that their view might have changed
        self._replaceView(oldView)
        
        self.viewChanged(view, oldView)
        
    def viewChanged(self, view, oldView):
        """Called when this item's view has changed
        (ie, the item has been added to or removed from a ViewBox)"""
        pass
        
    def _replaceView(self, oldView, item=None):
        if item is None:
            item = self
        for child in item.childItems():
            if isinstance(child, GraphicsItem):
                if child.getViewBox() is oldView:
                    child._updateView()
            else:
                self._replaceView(oldView, child)

    def viewRangeChanged(self):
        """
        Called whenever the view coordinates of the ViewBox containing this item have changed.
        """
        pass
    
    def viewTransformChanged(self):
        """
        Called whenever the transformation matrix of the view has changed.
        (eg, the view range has changed or the view was resized)
        """
        pass
        
    def informViewBoundsChanged(self):
        """
        Inform this item's container ViewBox that the bounds of this item have changed.
        This is used by ViewBox to react if auto-range is enabled.
        """
        view = self.getViewBox()
        if view is not None and hasattr(view, 'implements') and view.implements('ViewBox'):
            view.itemBoundsChanged(self)  ## inform view so it can update its range if it wants
    
    def childrenShape(self):
        """Return the union of the shapes of all descendants of this item in local coordinates."""
        shapes = [self.mapFromItem(c, c.shape()) for c in self.allChildItems()]
        return reduce(operator.add, shapes)
    
    def allChildItems(self, root=None):
        """Return list of the entire item tree descending from this item."""
        if root is None:
            root = self
        tree = []
        for ch in root.childItems():
            tree.append(ch)
            tree.extend(self.allChildItems(ch))
        return tree
    
    def setExportMode(self, export, opts=None):
        """
        This method is called by exporters to inform items that they are being drawn for export
        with a specific set of options. Items access these via self._exportOptions.
        When exporting is complete, _exportOptions is set to False.
        """
        if opts is None:
            opts = {}
        if export:
            self._exportOpts = opts
        else:
            self._exportOpts = False

    def getContextMenus(self, event):
        return [self.getMenu()] if hasattr(self, "getMenu") else []
