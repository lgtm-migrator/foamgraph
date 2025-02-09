"""
Distributed under the terms of the BSD 3-Clause License.

The full license is in the file LICENSE, distributed with this software.

Author: Jun Zhu
"""
import warnings
from itertools import chain

import numpy as np

from .backend.QtGui import QPainter
from .backend.QtCore import pyqtSignal, pyqtSlot, Qt
from .backend.QtWidgets import (
    QCheckBox, QGraphicsGridLayout, QHBoxLayout, QLabel, QMenu, QSizePolicy,
    QSlider, QWidget, QWidgetAction
)

from . import pyqtgraph_be as pg
from .pyqtgraph_be import Point
from .pyqtgraph_be import functions as fn
from .plot_items import CurvePlotItem, PlotItem
from .aesthetics import FColor


class ImageHistogramEditor(pg.GraphicsWidget):
    """GraphicsWidget for adjusting the display of an image.

    Implemented based on pyqtgraph.HistogramLUTItem.
    """

    lut_changed_sgn = pyqtSignal(object)

    def __init__(self, image_item, parent=None):
        super().__init__(parent=parent)
        self._lut = None

        gradient = pg.GradientEditorItem()
        gradient.setOrientation('right')
        gradient.loadPreset('grey')
        self._gradient = gradient
        self._gradient.show()

        lri = pg.LinearRegionItem([0, 1], 'horizontal', swapMode='block')
        lri.setZValue(1000)
        lri.lines[0].addMarker('<|', 0.5)
        lri.lines[1].addMarker('|>', 0.5)
        self._lri = lri

        self._hist = CurvePlotItem(pen=FColor.mkPen('k'))
        self._hist.rotate(90)

        vb = pg.ViewBox(parent=self)
        vb.setMaximumWidth(152)
        vb.setMinimumWidth(45)
        vb.setMouseEnabled(x=False, y=True)
        vb.addItem(self._hist)
        vb.addItem(self._lri)
        vb.enableAutoRange(pg.ViewBox.XYAxes)
        self._vb = vb

        self._axis = pg.AxisItem(
            'left', linkView=self._vb, maxTickLength=-10, parent=self)

        self.initUI()
        self.initConnections()

        image_item.image_changed_sgn.connect(self.onImageChanged)
        # send function pointer, not the result
        image_item.setLookupTable(self.getLookupTable)
        self._image_item = image_item
        # If image_item._image is None, the following line does not initialize
        # image_item._levels
        self.onImageChanged(auto_levels=True)
        # synchronize levels
        image_item.setLevels(self.getLevels())

    def initUI(self):
        layout = QGraphicsGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addItem(self._axis, 0, 0)
        layout.addItem(self._vb, 0, 1)
        layout.addItem(self._gradient, 0, 2)
        self.setLayout(layout)

    def initConnections(self):
        self._lri.sigRegionChanged.connect(self.regionChanging)
        self._lri.sigRegionChangeFinished.connect(self.regionChanged)

        self._gradient.sigGradientChanged.connect(self.gradientChanged)

        self._vb.sigRangeChanged.connect(self.update)

    def paint(self, p, *args):
        """Override."""
        pen = self._lri.lines[0].pen
        rgn = self.getLevels()
        p1 = self._vb.mapFromViewToItem(
            self, Point(self._vb.viewRect().center().x(), rgn[0]))
        p2 = self._vb.mapFromViewToItem(
            self, Point(self._vb.viewRect().center().x(), rgn[1]))

        rect = self._gradient.mapRectToParent(self._gradient.gradRect.rect())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        for pen in [fn.mkPen((0, 0, 0, 100), width=3), pen]:
            p.setPen(pen)
            p.drawLine(p1 + Point(0, 5), rect.bottomLeft())
            p.drawLine(p2 - Point(0, 5), rect.topLeft())
            p.drawLine(rect.topLeft(), rect.topRight())
            p.drawLine(rect.bottomLeft(), rect.bottomRight())

    def gradientChanged(self):
        if self._gradient.isLookupTrivial():
            # lambda x: x.astype(np.uint8))
            self._image_item.setLookupTable(None)
        else:
            # send function pointer, not the result
            self._image_item.setLookupTable(self.getLookupTable)

        self._lut = None
        self.lut_changed_sgn.emit(self)

    def getLookupTable(self, img=None, n=None, alpha=None):
        """Return the look-up table."""
        if self._lut is None:
            if n is None:
                n = 256 if img.dtype == np.uint8 else 512
            self._lut = self._gradient.getLookupTable(n, alpha=alpha)
        return self._lut

    def regionChanging(self):
        """One line of the region is being dragged."""
        self._image_item.setLevels(self.getLevels())
        self.update()

    def regionChanged(self):
        """Line dragging has finished."""
        self._image_item.setLevels(self.getLevels())

    def onImageChanged(self, auto_levels=False):
        hist, bin_centers = self._image_item.histogram()

        if hist is None:
            self._hist.setData([], [])
            return

        self._hist.setData(bin_centers, hist)
        if auto_levels:
            self._lri.setRegion((bin_centers[0], bin_centers[-1]))
        else:
            # synchronize levels if ImageItem updated its image with
            # auto_levels = True
            self._lri.setRegion(self._image_item.getLevels())

    def setColorMap(self, cm):
        self._gradient.setColorMap(cm)

    def getLevels(self):
        return self._lri.getRegion()

    def setLevels(self, levels):
        """Called by ImageHistogramEditor."""
        self._lri.setRegion(levels)


class PlotArea(pg.GraphicsWidget):
    """GraphicsWidget implementing a standard 2D plotting area with axes.

    Implemented based on pyqtgraph.PlotItem.

    It has the following functionalities:

    - Manage placement of a ViewBox, AxisItems, and LabelItems;
    - Manage a list of GraphicsItems displayed inside the ViewBox;
    - Implement a context menu with display options.
    """

    cross_toggled_sgn = pyqtSignal(bool)

    _METER_ROW = 0
    _TITLE_ROW = 1

    _MAX_ANNOTATION_ITEMS = 10

    def __init__(self, name=None, *,
                 enable_meter: bool = True,
                 enable_grid: bool = True,
                 enable_transform: bool = True,
                 parent=None):
        super().__init__(parent=parent)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._items = set()
        self._plot_items = set()
        self._plot_items2 = set()
        self._annotation_items = []
        self._n_vis_annotation_items = 0

        self._vb = pg.ViewBox(parent=self)
        self._vb2 = None

        if name is not None:
            self._vb.register(name)

        self._legend = None
        self._axes = {}
        self._meter = pg.LabelItem(
            '', size='11pt', justify='left', color='6A3D9A', parent=self)
        self._title = pg.LabelItem('', size='11pt', parent=self)

        # context menu
        self._show_cross_cb = QCheckBox("Cross cursor")

        self._show_x_grid_cb = QCheckBox("Show X Grid")
        self._show_y_grid_cb = QCheckBox("Show Y Grid")
        self._grid_opacity_sld = QSlider(Qt.Orientation.Horizontal)
        self._grid_opacity_sld.setMinimum(0)
        self._grid_opacity_sld.setMaximum(255)
        self._grid_opacity_sld.setValue(160)
        self._grid_opacity_sld.setSingleStep(1)

        self._log_x_cb = QCheckBox("Log X")
        self._log_y_cb = QCheckBox("Log Y")

        self._menus = []
        self._enable_meter = enable_meter
        self._enable_grid = enable_grid
        self._enable_transform = enable_transform

        self._show_meter = False

        self._layout = QGraphicsGridLayout()

        self.initUI()
        self.initConnections()

    def initUI(self):
        layout = self._layout

        layout.setContentsMargins(1, 1, 1, 1)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)

        layout.addItem(self._meter, self._METER_ROW, 1)
        layout.addItem(self._title, self._TITLE_ROW, 1)
        layout.addItem(self._vb, 3, 1)

        for i in range(5):
            layout.setRowPreferredHeight(i, 0)
            layout.setRowMinimumHeight(i, 0)
            layout.setRowSpacing(i, 0)
            layout.setRowStretchFactor(i, 1)

        for i in range(3):
            layout.setColumnPreferredWidth(i, 0)
            layout.setColumnMinimumWidth(i, 0)
            layout.setColumnSpacing(i, 0)
            layout.setColumnStretchFactor(i, 1)

        layout.setRowStretchFactor(2, 100)
        layout.setColumnStretchFactor(1, 100)

        self.setLayout(layout)

        self._initAxisItems()
        self.setTitle()
        self.showMeter(self._show_meter)

        self._initContextMenu()

    def initConnections(self):
        self._show_cross_cb.toggled.connect(self._onShowCrossChanged)

        self._show_x_grid_cb.toggled.connect(self._onShowGridChanged)
        self._show_y_grid_cb.toggled.connect(self._onShowGridChanged)
        self._grid_opacity_sld.sliderReleased.connect(self._onShowGridChanged)

        self._log_x_cb.toggled.connect(self._onLogXChanged)
        self._log_y_cb.toggled.connect(self._onLogYChanged)

    def _initMeterManu(self):
        menu = QMenu("Meter")
        self._menus.append(menu)

        cross_act = QWidgetAction(menu)
        cross_act.setDefaultWidget(self._show_cross_cb)
        menu.addAction(cross_act)

    def _initGridMenu(self):
        menu = QMenu("Grid")
        self._menus.append(menu)

        show_x_act = QWidgetAction(menu)
        show_x_act.setDefaultWidget(self._show_x_grid_cb)
        menu.addAction(show_x_act)
        show_y_act = QWidgetAction(menu)
        show_y_act.setDefaultWidget(self._show_y_grid_cb)
        menu.addAction(show_y_act)
        opacity_act = QWidgetAction(menu)
        widget = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Opacity"))
        layout.addWidget(self._grid_opacity_sld)
        widget.setLayout(layout)
        opacity_act.setDefaultWidget(widget)
        menu.addAction(opacity_act)

    def _initTransformMenu(self):
        menu = QMenu("Transform")
        self._menus.append(menu)

        log_x_act = QWidgetAction(menu)
        log_x_act.setDefaultWidget(self._log_x_cb)
        menu.addAction(log_x_act)
        log_y_act = QWidgetAction(menu)
        log_y_act.setDefaultWidget(self._log_y_cb)
        menu.addAction(log_y_act)

    def _initContextMenu(self):
        if self._enable_meter:
            self._initMeterManu()

        if self._enable_grid:
            self._initGridMenu()

        if self._enable_transform:
            self._initTransformMenu()

    def _initAxisItems(self):
        for orient, pos in (('top', (2, 1)),
                            ('bottom', (4, 1)),
                            ('left', (3, 0)),
                            ('right', (3, 2))):
            axis = pg.AxisItem(orientation=orient, parent=self)

            axis.linkToView(self._vb)
            self._axes[orient] = {'item': axis, 'pos': pos}
            self._layout.addItem(axis, *pos)
            axis.setZValue(-1000)
            axis.setFlag(axis.GraphicsItemFlag.ItemNegativeZStacksBehindParent)

            self.showAxis(orient, orient in ['left', 'bottom'])

    def getViewBox(self):
        return self._vb

    def clearAllPlotItems(self):
        """Clear data on all the plot items."""
        for item in chain(self._plot_items, self._plot_items2):
            item.setData([], [])

    @pyqtSlot(bool)
    def _onShowCrossChanged(self, state):
        self.showMeter(state)
        self.cross_toggled_sgn.emit(state)

    @pyqtSlot()
    def _onShowGridChanged(self):
        alpha = self._grid_opacity_sld.value()
        x = alpha if self._show_x_grid_cb.isChecked() else False
        y = alpha if self._show_y_grid_cb.isChecked() else False
        self.getAxis('bottom').setGrid(x)
        self.getAxis('left').setGrid(y)

    @pyqtSlot(bool)
    def _onLogXChanged(self, state):
        for item in chain(self._plot_items, self._plot_items2):
            item.setLogX(state)
        self.getAxis("bottom").setLogMode(state)
        self._vb.autoRange(disableAutoRange=False)

    @pyqtSlot(bool)
    def _onLogYChanged(self, state):
        for item in self._plot_items:
            item.setLogY(state)
        self.getAxis("left").setLogMode(state)
        self._vb.autoRange(disableAutoRange=False)

    def addItem(self, item, ignore_bounds=False, y2=False):
        """Add a graphics item to ViewBox."""
        if item in self._items:
            warnings.warn(f'Item {item} already added to PlotItem, ignoring.')
            return

        self._items.add(item)

        if isinstance(item, PlotItem):
            if y2:
                if self._log_x_cb.isChecked():
                    item.setLogX(True)

                self._plot_items2.add(item)
            else:
                if self._log_x_cb.isChecked():
                    item.setLogX(True)

                if self._log_y_cb.isChecked():
                    item.setLogY(True)

                self._plot_items.add(item)

            name = item.name()
            if self._legend is not None and name:
                self._legend.addItem(item, name)

        if y2:
            vb = self._vb2
            if vb is None:
                vb = pg.ViewBox()
                self.scene().addItem(vb)
                right_axis = self.getAxis('right')
                right_axis.linkToView(vb)
                right_axis.show()
                vb.setXLink(self._vb)
                self._vb2 = vb
                self._vb.sigResized.connect(self._updateY2View)
        else:
            vb = self._vb

        vb.addItem(item, ignoreBounds=ignore_bounds)

    def _updateY2View(self):
        self._vb2.setGeometry(self._vb.sceneBoundingRect())
        # not sure this is required
        # vb.linkedViewChanged(self._plot_area.vb, vb.XAxis)

    def removeItem(self, item):
        """Add a graphics item to ViewBox."""
        if item not in self._items:
            return

        if item in self._annotation_items:
            # it is tricky to update n_vis_annotation_items
            raise RuntimeError("Annotation item is not allowed to be removed "
                               "using 'removeItem' method!")

        self._items.remove(item)

        if item in self._plot_items2:
            self._plot_items2.remove(item)
            if self._legend is not None and item.name():
                self._legend.removeItem(item)
            self._vb2.removeItem(item)
            return

        if item in self._plot_items:
            self._plot_items.remove(item)
            if self._legend is not None and item.name():
                self._legend.removeItem(item)

        self._vb.removeItem(item)

    def removeAllItems(self):
        """Remove all graphics items from the ViewBox."""
        for item in self._items:
            if item in self._plot_items2:
                self._vb2.removeItem(item)
            else:
                self._vb.removeItem(item)

        if self._legend is not None:
            self._legend.clear()

        self._plot_items.clear()
        self._plot_items2.clear()
        self._annotation_items.clear()
        self._n_vis_annotation_items = 0
        self._items.clear()

    def getContextMenus(self, event):
        """Override."""
        return self._menus

    def getAxis(self, axis):
        """Return the specified AxisItem.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        """
        return self._axes[axis]['item']

    def showAxis(self, axis, show=True):
        """Show or hide the given axis.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        :param bool show: whether to show the axis.
        """
        s = self.getAxis(axis)
        if show:
            s.show()
        else:
            s.hide()

    def addLegend(self, offset=(30, 30), **kwargs):
        """Add a LegendItem if it does not exist."""
        if self._legend is None:
            self._legend = pg.LegendItem(offset=offset, pen='k', **kwargs)
            self._legend.setParentItem(self._vb)

            for item in chain(self._plot_items, self._plot_items2):
                name = item.name()
                if name:
                    self._legend.addItem(item, name)

        return self._legend

    def showLegend(self, show=True):
        """Show or hide the legend.

        :param bool show: whether to show the legend.
        """
        if show:
            self._legend.show()
        else:
            self._legend.hide()

    def setLabel(self, axis, text=None, units=None, **args):
        """Set the label for an axis. Basic HTML formatting is allowed.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        :param str text: text to display along the axis. HTML allowed.
        """
        self.getAxis(axis).setLabel(text=text, units=units, **args)
        self.showAxis(axis)

    def showLabel(self, axis, show=True):
        """Show or hide one of the axis labels.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        :param bool show: whether to show the label.
        """
        self.getAxis(axis).showLabel(show)

    def showMeter(self, show=True):
        """Show or hide the meter bar.

        :param bool show: whether to show the meter bar.
        """
        row = self._METER_ROW
        if not show:
            self._meter.setMaximumHeight(0)
            self._layout.setRowFixedHeight(row, 0)
            self._meter.setVisible(False)
        else:
            self._meter.setMaximumHeight(30)
            self._layout.setRowFixedHeight(row, 30)
            self._meter.setVisible(True)

        self._show_meter = show

    def setMeter(self, pos):
        """Set the meter of the plot."""
        if not self._show_meter:
            return

        if pos is None:
            self._meter.setText("")
        else:
            x, y = pos
            self._meter.setText(f"x = {x}, y = {y}")

    def setAnnotationList(self, x, y, values=None):
        """Set a list of annotation items.

        :param list-like x: x coordinate of the annotated point.
        :param list-like y: y coordinate of the annotated point.
        :param list-like values: a list of annotation text.
        """

        # Don't waste time to check the list lengths.

        a_items = self._annotation_items

        if values is None:
            values = x
        values = values[:self._MAX_ANNOTATION_ITEMS]
        n_pts = len(values)

        n_items = len(a_items)
        if n_items < n_pts:
            for i in range(n_pts - n_items):
                item = pg.TextItem(color=FColor.mkColor('b'), anchor=(0.5, 2))
                self.addItem(item)
                a_items.append(item)

        n_vis = self._n_vis_annotation_items
        if n_vis < n_pts:
            for i in range(n_vis, n_pts):
                a_items[i].show()
        elif n_vis > n_pts:
            for i in range(n_pts, n_vis):
                a_items[i].hide()
        self._n_vis_annotation_items = n_pts

        for i in range(n_pts):
            a_items[i].setPos(x[i], y[i])
            a_items[i].setText(f"{values[i]:.4f}")

    def setTitle(self, *args, **kwargs):
        """Set the title of the plot."""
        row = self._TITLE_ROW
        title = None if len(args) == 0 else args[0]
        if title is None:
            self._title.setMaximumHeight(0)
            self._layout.setRowFixedHeight(row, 0)
            self._title.setVisible(False)
        else:
            self._title.setMaximumHeight(30)
            self._layout.setRowFixedHeight(row, 30)
            self._title.setText(title, **kwargs)
            self._title.setVisible(True)

    def setAspectLocked(self, *args, **kwargs):
        self._vb.setAspectLocked(*args, **kwargs)

    def invertX(self, *args, **kwargs):
        self._vb.invertX(*args, **kwargs)

    def invertY(self, *args, **kwargs):
        self._vb.invertY(*args, **kwargs)

    def autoRange(self, *args, **kwargs):
        self._vb.autoRange(*args, **kwargs)

    def mapSceneToView(self, *args, **kwargs):
        return self._vb.mapSceneToView(*args, **kwargs)
