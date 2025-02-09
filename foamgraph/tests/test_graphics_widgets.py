import unittest
from unittest.mock import patch

from foamgraph.backend.QtTest import QSignalSpy

from foamgraph import mkQApp
from foamgraph.graphics_widgets import ImageHistogramEditor, PlotArea
from foamgraph.image_items import ImageItem, RectROI
from foamgraph.plot_items import (
    CurvePlotItem, BarGraphItem, ScatterPlotItem, ErrorbarItem
)
from foamgraph import pyqtgraph_be as pg


app = mkQApp()


class TestPlotArea(unittest.TestCase):
    def setUp(self):
        self._view = pg.GraphicsView()
        self._area = PlotArea()
        self._area.removeAllItems()  # axis items etc. should not be affected

        # FIXME: need the following line because of the implementation of ViewBox
        self._view.setCentralWidget(self._area)

    def testAxes(self):
        area = self._area

        self.assertEqual(4, len(area._axes))
        for name, pos in [('left', (3, 0)), ('bottom', (4, 1))]:
            left_axis = area._axes[name]
            self.assertIsInstance(left_axis['item'], pg.AxisItem)
            self.assertTrue(left_axis['item'].isVisible())
            self.assertTupleEqual(pos, left_axis['pos'])
            self.assertIs(area.getAxis(name), left_axis['item'])

            with patch.object(left_axis['item'], "show") as mocked:
                area.showAxis(name)
                mocked.assert_called_once()

            with patch.object(left_axis['item'], "hide") as mocked:
                area.showAxis(name, False)
                mocked.assert_called_once()

            with patch.object(left_axis['item'], "setLabel") as mocked:
                area.setLabel(name, "abc")
                mocked.assert_called_once_with(text="abc", units=None)

            with patch.object(left_axis['item'], "showLabel") as mocked:
                area.showLabel(name)
                mocked.assert_called_once()

        for name in ['top', 'right']:
            self.assertFalse(area.getAxis(name).isVisible())

    def testLegend(self):
        area = self._area
        self.assertIsNone(area._legend)

        legend = area.addLegend((-30, -30))
        self.assertIsInstance(area._legend, pg.LegendItem)
        self.assertIs(legend, area._legend)

        # test addLegend when legend already exists
        area.addLegend((-10, -10))
        self.assertIsInstance(area._legend, pg.LegendItem)
        self.assertIs(legend, area._legend)

    def testTitle(self):
        area = self._area
        self.assertIsInstance(area._title, pg.LabelItem)

        self.assertEqual(0, area._title.maximumHeight())
        self.assertFalse(area._title.isVisible())

        area.setTitle("abcdefg")
        self.assertGreater(area._title.maximumHeight(), 0)
        self.assertTrue(area._title.isVisible())

    def testForwardMethod(self):
        area = self._area

        for method in ["setAspectLocked", "invertY", "invertX", "mapSceneToView"]:
            with patch.object(area._vb, method) as mocked:
                getattr(area, method)()
                mocked.assert_called_once()

    def testPlotItemManipulation(self):
        area = self._area

        image_item = ImageItem()
        area.addItem(image_item)
        area.addItem(RectROI(0))
        bar_graph_item = BarGraphItem(name="bar")
        area.addItem(bar_graph_item, y2=True)
        errorbar_item = ErrorbarItem()
        area.addItem(errorbar_item)

        area.addLegend()  # add legend when there are already added PlotItems

        curve_plot_item = CurvePlotItem(name="curve")
        area.addItem(curve_plot_item)
        scatter_plot_item = ScatterPlotItem(name="scatter")
        area.addItem(scatter_plot_item)
        area.setAnnotationList([0], [0], [1])

        self.assertEqual(3, len(area._plot_items))
        self.assertEqual(1, len(area._plot_items2))
        self.assertEqual(7, len(area._items))
        self.assertEqual(6, len(area._vb.addedItems))
        self.assertEqual(1, len(area._vb2.addedItems))
        self.assertEqual(3, len(area._legend.items))
        self.assertEqual(1, len(area._annotation_items))

        with patch.object(curve_plot_item, "setData") as mocked1:
            with patch.object(bar_graph_item, "setData") as mocked2:
                area.clearAllPlotItems()
                mocked1.assert_called_once()
                mocked2.assert_called_once()

        # remove an item which does not exist
        area.removeItem(BarGraphItem())
        self.assertEqual(3, len(area._plot_items))
        self.assertEqual(1, len(area._plot_items2))
        self.assertEqual(7, len(area._items))
        self.assertEqual(6, len(area._vb.addedItems))
        self.assertEqual(1, len(area._vb2.addedItems))
        self.assertEqual(3, len(area._legend.items))

        # remove an existing item
        area.removeItem(bar_graph_item)
        self.assertEqual(3, len(area._plot_items))
        self.assertEqual(0, len(area._plot_items2))
        self.assertEqual(6, len(area._items))
        self.assertEqual(6, len(area._vb.addedItems))
        self.assertEqual(0, len(area._vb2.addedItems))
        self.assertEqual(2, len(area._legend.items))

        # remove an existing item which is not a PlotItem
        area.removeItem(image_item)
        self.assertEqual(3, len(area._plot_items))
        self.assertEqual(0, len(area._plot_items2))
        self.assertEqual(5, len(area._items))
        self.assertEqual(5, len(area._vb.addedItems))
        self.assertEqual(0, len(area._vb2.addedItems))
        self.assertEqual(2, len(area._legend.items))

        # remove a PlotItem which does not has a name and hence was not added
        # into the legend
        area.removeItem(errorbar_item)
        self.assertEqual(2, len(area._legend.items))

        with self.assertRaisesRegex(RuntimeError, "not allowed to be removed"):
            area.removeItem(area._annotation_items[0])

        area.removeAllItems()
        self.assertEqual(0, len(area._plot_items))
        self.assertEqual(0, len(area._plot_items2))
        self.assertEqual(0, len(area._items))
        self.assertEqual(0, len(area._vb.addedItems))
        self.assertEqual(0, len(area._vb2.addedItems))
        self.assertEqual(0, len(area._legend.items))

    def testContextMenu(self):
        area = self._area
        event = object()
        menus = self._area.getContextMenus(event)

        self.assertEqual(3, len(menus))
        self.assertEqual("Meter", menus[0].title())
        self.assertEqual("Grid", menus[1].title())
        self.assertEqual("Transform", menus[2].title())

        # test "Meter" actions
        meter_actions = menus[0].actions()
        self.assertFalse(area._show_meter)
        self.assertFalse(area._meter.isVisible())
        spy = QSignalSpy(area.cross_toggled_sgn)
        meter_actions[0].defaultWidget().setChecked(True)
        self.assertTrue(area._show_meter)
        self.assertTrue(area._meter.isVisible())
        self.assertEqual(1, len(spy))
        meter_actions[0].defaultWidget().setChecked(False)
        self.assertFalse(area._show_meter)
        self.assertFalse(area._meter.isVisible())
        self.assertEqual(2, len(spy))

        # test "Grid" actions
        grid_actions = menus[1].actions()
        alpha = area._grid_opacity_sld.value()
        grid_actions[0].defaultWidget().setChecked(True)
        self.assertEqual(alpha, area.getAxis("bottom").grid)
        grid_actions[1].defaultWidget().setChecked(True)
        self.assertEqual(alpha, area.getAxis("left").grid)

        # test "Transform" actions
        plot_item = CurvePlotItem()
        plot_item2 = ScatterPlotItem()
        area.addItem(plot_item)
        area.addItem(plot_item2, y2=True)
        transform_actions = menus[2].actions()

        with patch.object(plot_item, "updateGraph") as mocked:
            with patch.object(plot_item2, "updateGraph") as mocked2:
                transform_actions[0].defaultWidget().setChecked(True)
                self.assertTrue(area.getAxis("bottom").logMode)
                # self.assertTrue(area.getAxis("top").logMode)
                self.assertTrue(plot_item._log_x_mode)
                self.assertTrue(plot_item2._log_x_mode)
                mocked.assert_called_once()
                mocked2.assert_called_once()

                plot_item3 = CurvePlotItem()
                plot_item4 = ScatterPlotItem()
                area.addItem(plot_item3)
                area.addItem(plot_item4, y2=True)
                self.assertTrue(plot_item3._log_x_mode)
                self.assertTrue(plot_item4._log_x_mode)

        with patch.object(plot_item, "updateGraph") as mocked:
            with patch.object(plot_item2, "updateGraph") as mocked2:
                transform_actions[1].defaultWidget().setChecked(True)
                self.assertTrue(area.getAxis("left").logMode)
                # self.assertTrue(area.getAxis("right").logMode)
                self.assertTrue(plot_item._log_y_mode)
                self.assertFalse(plot_item2._log_y_mode)
                mocked.assert_called_once()
                mocked2.assert_not_called()

                plot_item5 = CurvePlotItem()
                plot_item6 = ScatterPlotItem()
                area.addItem(plot_item5)
                area.addItem(plot_item6, y2=True)
                self.assertTrue(plot_item5._log_y_mode)
                self.assertFalse(plot_item6._log_y_mode)

        another_area = PlotArea(
            enable_meter=False, enable_transform=False, enable_grid=False)
        menus = another_area.getContextMenus(event)
        self.assertEqual(0, len(menus))

    def testSetAnnotationList(self):
        area = self._area
        # add some items to simulate the practical situation
        area.addItem(ImageItem())
        area.addItem(BarGraphItem())
        area.addItem(ErrorbarItem())

        # add some items
        area.setAnnotationList([1, 2, 3], [4, 5, 6])
        self.assertEqual(3, len(area._annotation_items))
        for item in area._annotation_items:
            self.assertTrue(item.isVisible())
        self.assertEqual(3, area._n_vis_annotation_items)

        # set less items
        area.setAnnotationList([1, 2], [4, 5])
        self.assertEqual(3, len(area._annotation_items))
        for item in area._annotation_items[:2]:
            self.assertTrue(item.isVisible())
        self.assertFalse(area._annotation_items[-1].isVisible())
        self.assertEqual(2, area._n_vis_annotation_items)

        # set more items
        area.setAnnotationList([1, 2, 3, 4], [4, 5, 6, 7], values=[4, 5, 6, 7])
        self.assertEqual(4, len(area._annotation_items))
        for item in area._annotation_items:
            self.assertTrue(item.isVisible())
        self.assertEqual(4, area._n_vis_annotation_items)

        # clear items
        area.setAnnotationList([], [])
        self.assertEqual(4, len(area._annotation_items))
        for item in area._annotation_items:
            self.assertFalse(item.isVisible())
        self.assertEqual(0, area._n_vis_annotation_items)

        area.removeAllItems()
        self.assertEqual(0, len(area._annotation_items))
        self.assertEqual(0, area._n_vis_annotation_items)

        # test TextItem call
        with patch("foamgraph.pyqtgraph_be.TextItem.setPos") as mocked_pos:
            with patch("foamgraph.pyqtgraph_be.TextItem.setText") as mocked_value:
                area.setAnnotationList([1, 2, 3], [4, 5, 6])
                mocked_pos.assert_called_with(3, 6)
                mocked_value.assert_called_with("3.0000")

                area.setAnnotationList([1], [4], [2])
                mocked_value.assert_called_with("2.0000")


class TestImageHistogramEditor(unittest.TestCase):
    def testGeneral(self):
        image_item = ImageItem()
        item = ImageHistogramEditor(image_item, parent=None)
