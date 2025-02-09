import pytest

import numpy as np

from foamgraph.backend.QtCore import QByteArray, QDataStream, QIODevice, QPointF, QRectF
from foamgraph import mkQApp, PlotWidgetF
from foamgraph.plot_items import (
    CurvePlotItem, BarGraphItem, ScatterPlotItem, ErrorbarItem
)

from . import _display

app = mkQApp()


class TestPlotItems:
    @classmethod
    def setup_class(cls):
        cls._widget = PlotWidgetF()
        if _display():
            cls._widget.show()

    def teardown_method(self):
        self._widget.removeAllItems()

    def testCurvePlotItemArray2Path(self):
        size = 5
        x = np.arange(size)
        y = 2 * np.arange(size)
        item = CurvePlotItem(x, y)
        self._widget.addItem(item)
        p = item._graph

        # stream path
        arr = QByteArray()
        buf = QDataStream(arr, QIODevice.OpenModeFlag.ReadWrite)
        buf << p
        buf.device().reset()

        # test protocol
        assert arr.size() == 4 + size * 20 + 8
        assert buf.readInt32() == size
        for i in range(5):
            if i == 0:
                assert buf.readInt32() == 0
            else:
                assert buf.readInt32() == 1
            assert buf.readDouble() == x[i]
            assert buf.readDouble() == y[i]
        assert buf.readInt32() == 0
        assert buf.readInt32() == 0

    def testCurvePlotItemCheckFinite(self):
        item = CurvePlotItem(check_finite=False)
        self._widget.addItem(item)
        # nan and infinite values prevent generating plots
        x = [1, 2, 3, 4, 5]
        y = [1, 2, 3, np.nan, 5]
        item.setData(x, y)
        # FIXME
        # assert QRectF() == item.boundingRect()
        self._widget.removeItem(item)

        item2 = CurvePlotItem(check_finite=True)
        self._widget.addItem(item2)
        item2.setData(x, y)
        assert QRectF(1., 0., 4., 5.) == item2.boundingRect()

    @pytest.mark.parametrize("dtype", [float, np.int64, np.uint16])
    def testCurvePlotItem(self, dtype):
        x = np.arange(10).astype(dtype)
        y = x * 1.5

        # x and y are lists
        item = CurvePlotItem(x.tolist(), y.tolist(), name='line')
        self._widget.addItem(item)
        self._widget.addLegend()
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)

        # x and y are numpy.arrays
        # item.setData(x, y)
        if dtype == float:
            _display()

        # test different lengths
        with pytest.raises(ValueError, match="different lengths"):
            item.setData(np.arange(2).astype(dtype), np.arange(3).astype(dtype))

        # test log mode
        self._widget._plot_area._onLogXChanged(True)
        if dtype == float:
            _display()
        assert item.boundingRect() == QRectF(0, 0, 1.0, 13.5)
        self._widget._plot_area._onLogYChanged(True)
        if dtype == float:
            _display()
        assert item.boundingRect().topLeft() == QPointF(0, 0)
        assert item.boundingRect().bottomRight().x() == 1.0
        assert 1.2 > item.boundingRect().bottomRight().y() > 1.1

        # clear data
        item.setData([], [])
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)
        if dtype == float:
            _display()

    def testBarGraphItem(self, dtype=np.float32):
        x = np.arange(10).astype(dtype)
        y = x * 1.5

        # x and y are lists
        item = BarGraphItem(x.tolist(), y.tolist(), name='bar')
        self._widget.addItem(item)
        self._widget.addLegend()
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)

        # x and y are numpy.arrays
        item.setData(x, y)
        _display()

        # test different lengths
        with pytest.raises(ValueError, match="different lengths"):
            item.setData(np.arange(2), np.arange(3))

        # test log mode
        self._widget._plot_area._onLogXChanged(True)
        _display()
        assert item.boundingRect() == QRectF(-1.0, 0, 3.0, 14.0)
        self._widget._plot_area._onLogYChanged(True)
        _display()
        assert item.boundingRect() == QRectF(-1.0, 0, 3.0, 2.0)

        # clear data
        item.setData([], [])
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)
        _display()

    def testErrorbarItem(self, dtype=np.float32):
        x = np.arange(10).astype(dtype)
        y = np.arange(10).astype(dtype)

        # x and y are lists
        item = ErrorbarItem(x.tolist(), y.tolist(), name='errorbar')
        self._widget.addItem(item)
        self._widget.addLegend()
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)
        assert isinstance(item._y_min, np.ndarray)
        assert isinstance(item._y_max, np.ndarray)

        # x and y are numpy.arrays
        y_min = y - 1
        y_max = y + 1
        item.setBeam(1)
        item.setData(x, y, y_min=y_min, y_max=y_max)
        _display()

        # test different lengths
        with pytest.raises(ValueError, match="different lengths"):
            item.setData(np.arange(2), np.arange(3))

        with pytest.raises(ValueError, match="different lengths"):
            item.setData(np.arange(2), np.arange(2), y_min=np.arange(3), y_max=np.arange(2))

        with pytest.raises(ValueError, match="different lengths"):
            item.setData(np.arange(2), np.arange(2), y_min=np.arange(2), y_max=np.arange(3))

        # test log mode
        self._widget._plot_area._onLogXChanged(True)
        _display()
        assert item.boundingRect() == QRectF(-0.5, -1.0, 2.0, 11.0)
        self._widget._plot_area._onLogYChanged(True)
        _display()
        assert item.boundingRect().topLeft() == QPointF(-0.5, 0.0)
        assert 1.5, item.boundingRect().bottomRight().x()
        assert 1.0 < item.boundingRect().bottomRight().y() < 1.1

        # clear data
        item.setData([], [])
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)
        _display()

    def testScatterPlotItemSymbols(self):
        for sym in ScatterPlotItem._symbol_map:
            x = np.arange(10)
            y = np.arange(10)
            item = ScatterPlotItem(x, y, name=sym, symbol=sym, size=np.random.randint(15, 30))
            self._widget.removeAllItems()
            self._widget.addItem(item)
            self._widget.addLegend()
            _display(interval=0.2)

    def testScatterPlotItem(self, dtype=float):
        x = np.arange(10).astype(dtype)
        y = x * 1.5

        # x and y are lists
        item = ScatterPlotItem(x.tolist(), y.tolist(), name='scatter')
        self._widget.addItem(item)
        self._widget.addLegend()
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)

        # x and y are numpy.arrays
        item.setData(x, y)
        if dtype == float:
            _display()

        # test different lengths
        with pytest.raises(ValueError, match="different lengths"):
            item.setData(np.arange(2).astype(dtype), np.arange(3).astype(dtype))

        # test log mode
        self._widget._plot_area._onLogXChanged(True)
        if dtype == float:
            _display()
        assert -0.2 < item.boundingRect().topLeft().x() < 0
        assert -0.22 < item.boundingRect().topLeft().y() < -0.2
        assert 1.0 < item.boundingRect().bottomRight().x() < 1.2
        assert 13.5 < item.boundingRect().bottomRight().y() < 14.0

        self._widget._plot_area._onLogYChanged(True)
        if dtype == float:
            _display()
        assert -0.1 < item.boundingRect().topLeft().x() < 0
        assert -0.1 < item.boundingRect().topLeft().y() < 0
        assert 1.0 < item.boundingRect().bottomRight().x() < 1.1
        assert 1.0 < item.boundingRect().bottomRight().y() < 1.2

        # clear data
        item.setData([], [])
        assert isinstance(item._x, np.ndarray)
        assert isinstance(item._y, np.ndarray)
        if dtype == float:
            _display()
