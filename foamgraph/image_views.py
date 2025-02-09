"""
Distributed under the terms of the BSD 3-Clause License.

The full license is in the file LICENSE, distributed with this software.

Author: Jun Zhu
"""
import abc
from typing import final

import numpy as np

from .backend.QtCore import pyqtSlot, Qt, QTimer
from .backend.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from . import pyqtgraph_be as pg

from .aesthetics import colorMapFactory
from .config import config
from .graphics_widgets import ImageHistogramEditor
from .plot_widgets import PlotWidgetF
from .image_items import ImageItem, RectROI


class HistogramLUTWidget(pg.GraphicsView):
    def __init__(self, image_item, parent=None):
        super().__init__(parent)

        if not isinstance(image_item, ImageItem):
            raise TypeError

        self._item = ImageHistogramEditor(image_item)
        self.setCentralWidget(self._item)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(95)

    def setColorMap(self, cm):
        self._item.setColorMap(cm)


class ImageViewF(QWidget):
    """ImageView base class.

    A widget used for displaying 2D image data.

    Note: it is different from the ImageView in pyqtgraph!

    Attributes:
        _image_item (pyqtgraph.ImageItem): This object will be used to
            display the image.
    """
    def __init__(self, *,
                 hide_axis: bool = True,
                 color_map=None,
                 n_rois: int = 0,
                 roi_position: tuple = (0, 0),
                 roi_size: tuple = (100, 100),
                 parent=None):
        """Initialization.

        :param n_roi: Number of ROIs included.
        :param hide_axis: True for hiding left and bottom axes.
        :param roi_position: Initial upper-left corner position (x, y)
            of the first ROI.
        :param roi_size: Initial size (w, h) of all ROIs.
        """
        super().__init__(parent=parent)

        self._mouse_hover_v_rounding_decimals = 1

        self._rois = []
        self._roi_colors = ['b', 'r', 'g', 'o']
        if n_rois > 4:
            raise ValueError("Maximum number of ROIs is 4.")
        self._initializeROIs(n_rois, roi_position, roi_size)

        self._plot_widget = PlotWidgetF(enable_meter=False,
                                        enable_grid=False,
                                        enable_transform=False)

        self._cached_title = None
        # use the public interface for caching
        self.setTitle("")  # reserve space for display

        if hide_axis:
            self._plot_widget.hideAxis()

        self._image_item = ImageItem()
        self._plot_widget.addItem(self._image_item)
        self._image_item.mouse_moved_sgn.connect(self.onMouseMoved)

        for roi in self._rois:
            self._plot_widget.addItem(roi)

        self.invertY(True)  # y-axis points from top to bottom
        self.setAspectLocked(True)

        self._hist_widget = HistogramLUTWidget(self._image_item)

        if color_map is None:
            self.setColorMap(colorMapFactory[config["COLOR_MAP"]])
        else:
            self.setColorMap(colorMapFactory["thermal"])

        self._is_initialized = False
        self._image = None

        self.initUI()

        if parent is not None and hasattr(parent, 'registerPlotWidget'):
            parent.registerPlotWidget(self)

    def initUI(self):
        layout = QHBoxLayout()
        layout.addWidget(self._plot_widget, 4)
        layout.addWidget(self._hist_widget, 1)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def reset(self):
        self.clear()

    def addRoiController(self, controller: QWidget):
        """Add control widget for the ROIs."""
        for roi in self._rois:
            controller.addRoi(roi)

    @abc.abstractmethod
    def updateF(self, data):
        """This method is called by the parent window.

        The subclass should re-implement this method and call self.setImage
        in this method.
        """
        raise NotImplementedError

    def _initializeROIs(self, n, pos, size):
        for i in range(n):
            roi = RectROI(i + 1,
                          pos=(pos[0] + 10*i, pos[1] + 10*i),
                          size=size,
                          color=self._roi_colors[i])
            roi.hide()
            self._rois.append(roi)

    def updateROI(self, data):
        """Update ROIs.

        Update ROI through data instead of passing signals to ensure that
        visualization of ROIs and calculation of ROI data are synchronized.
        """
        for i, roi in enumerate(self._rois, 1):
            x, y, w, h = getattr(getattr(data.roi, f"geom{i}"), "geometry")
            if w > 0 and h > 0:
                roi.show()
                roi.setSize((w, h), update=False)
                roi.setPos((x, y), update=False)
            else:
                roi.hide()

    @property
    def image(self):
        return self._image

    @property
    def rois(self):
        return self._rois

    def setImage(self, *args, **kwargs):
        """Interface method."""
        self._updateImageImp(*args, **kwargs)

    def _updateImageImp(self, img, *, auto_range=False, auto_levels=False,
                        scale=None, pos=None):
        """Update the current displayed image.

        :param np.ndarray img: the image to be displayed.
        :param bool auto_range: whether to scale/pan the view to fit
            the image. default = False
        :param bool auto_levels: whether to update the white/black levels
            to fit the image. default = False
        :param tuple/list pos: the origin of the displayed image in (x, y).
        :param tuple/list scale: the origin of the displayed image image in
            (x_scale, y_scale).
        """
        if img is None:
            self.clear()
            return

        if not isinstance(img, np.ndarray):
            raise TypeError("Image data must be a numpy array!")

        self._image_item.setImage(img, auto_levels=auto_levels)
        self._image = img

        self._image_item.resetTransform()

        if scale is not None:
            self._image_item.scale(*scale)
        if pos is not None:
            self._image_item.setPos(*pos)

        if auto_range:
            self.autoRange()

    def clear(self):
        self._image = None
        # FIXME: there is a bug in ImageItem.setImage if the input is None
        self._image_item.clear()

    @pyqtSlot()
    def _onAutoLevel(self):
        if self.isVisible():
            self.updateImage(auto_levels=True)

    def updateImage(self, **kwargs):
        """Re-display the current image."""
        if self._image is None:
            return
        self._updateImageImp(self._image, **kwargs)

    def setMouseHoverValueRoundingDecimals(self, v):
        self._mouse_hover_v_rounding_decimals = v

    @pyqtSlot(int, int, float)
    def onMouseMoved(self, x, y, v):
        if x < 0 or y < 0:
            self._plot_widget.setTitle(self._cached_title)
        else:
            self._plot_widget.setTitle(
                f'x={x}, y={y}, '
                f'value={round(v, self._mouse_hover_v_rounding_decimals)}')

    def setLevels(self, *args, **kwargs):
        """Set the min/max (bright and dark) levels.

        See ImageHistogramEditor.setLevels.
        """
        self._hist_widget.setLevels(*args, **kwargs)

    def setColorMap(self, cm):
        """Set colormap for the displayed image.

        :param cm: a ColorMap object.
        """
        self._hist_widget.setColorMap(cm)

    def setAspectLocked(self, *args, **kwargs):
        self._plot_widget.setAspectLocked(*args, **kwargs)

    def setLabel(self, *args, **kwargs):
        self._plot_widget.setLabel(*args, **kwargs)

    def setTitle(self, *args, **kwargs):
        # This is the public interface. Therefore, we ought to cache
        # the title.
        self._cached_title = None if len(args) == 0 else args[0]
        self._plot_widget.setTitle(*args, **kwargs)

    def invertX(self, *args, **kwargs):
        self._plot_widget.invertX(*args, **kwargs)

    def invertY(self, *args, **kwargs):
        self._plot_widget.invertY(*args, **kwargs)

    def autoRange(self, *args, **kwargs):
        self._plot_widget.autoRange(*args, **kwargs)

    def addItem(self, *args, **kwargs):
        self._plot_widget.addItem(*args, **kwargs)

    def removeItem(self, *args, **kwargs):
        self._plot_widget.removeItem(*args, **kwargs)

    def closeEvent(self, event):
        """Override."""
        parent = self.parent()
        if parent is not None:
            parent.unregisterPlotWidget(self)
        super().closeEvent(event)


class TimedImageViewF(ImageViewF):
    def __init__(self, interval: int = 1000, *args, **kwargs):
        """Initialization.

        :param interval: Image updating interval in milliseconds.
        """
        super().__init__(*args, **kwargs)

        self._data = None

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh_imp)
        self._timer.start(interval)

    @abc.abstractmethod
    def refresh(self):
        pass

    def _refresh_imp(self):
        if self._data is not None:
            self.refresh()

    @final
    def updateF(self, data):
        """Override."""
        self._data = data
