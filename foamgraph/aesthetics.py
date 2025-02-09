"""
Distributed under the terms of the BSD 3-Clause License.

The full license is in the file LICENSE, distributed with this software.

Author: Jun Zhu
"""
from typing import Union

from .backend.QtCore import Qt
from .backend.QtGui import QBrush, QColor, QPen, QPalette

from .pyqtgraph_be import ColorMap
from .pyqtgraph_be.graphicsItems.GradientEditorItem import Gradients

from .config import config


class QualitativeColor:

    foreground = config["FOREGROUND_COLOR"]  # black
    background = config["BACKGROUND_COLOR"]  # white-like

    k = (0, 0, 0)  # black
    n = (251, 154, 153)  # pink
    r = (227, 26, 28)  # red
    o = (255, 127, 0)  # orange
    y = (255, 255, 153)  # yellow
    c = (166, 206, 227)  # cyan
    b = (31, 120, 180)  # blue
    s = (178, 223, 138)  # grass green
    g = (51, 160, 44)  # green
    p = (106, 61, 154)  # purple
    d = (202, 178, 214)  # orchid
    w = (177, 89, 40)  # brown
    i = (192, 192, 192)  # silver

    @classmethod
    def mkColor(cls, c, *, alpha=255):
        return QColor(*getattr(cls, c), alpha)

    @classmethod
    def mkPen(cls, c, *, alpha=255, width=1, style=Qt.PenStyle.SolidLine):
        if c is None:
            return QPen(QColor(0, 0, 0, 0), width, Qt.PenStyle.NoPen)
        pen = QPen(QColor(*getattr(cls, c), alpha), width, style)
        pen.setCosmetic(True)
        return pen

    @classmethod
    def mkBrush(cls, c, *, alpha=255):
        if c is None:
            return QBrush(QColor(0, 0, 0, 0), Qt.BrushStyle.NoBrush)
        return QBrush(QColor(*getattr(cls, c), alpha))


FColor = QualitativeColor


class SequentialColor:

    # red
    r = [
        (153, 0, 13),
        (203, 24, 29),
        (239, 59, 44),
        (251, 106, 74),
        (252, 146, 114)
    ]
    # blue
    b = [
        (158, 202, 225),
        (107, 174, 214),
        (66, 146, 198),
        (33, 113, 181),
        (8, 69, 148),
    ]
    # magenta
    m = [
        (74, 20, 134),
        (106, 81, 163),
        (128, 125, 186),
        (158, 154, 200),
        (188, 189, 220)
    ]
    # green
    g = [
        (161, 217, 155),
        (116, 196, 118),
        (65, 171, 93),
        (35, 139, 69),
        (0, 90, 50),
    ]

    pool = r + b + m + g

    @classmethod
    def _validate_n(cls, n):
        if not isinstance(n, int) or n <= 0:
            raise ValueError("n must be a positive integer!")

    @classmethod
    def mkColor(cls, n, *, alpha=255):
        """Generate n QColors via sequential colors.

        The colors will be repeated if n is larger than the number of
        pre-defined colors.

        :param int n: number of colors.
        """
        cls._validate_n(n)
        lst = cls.pool * (int(n/len(cls.pool)) + 1)
        for c in lst[:n]:
            yield QColor(*c, alpha)

    @classmethod
    def mkPen(cls, n, *, alpha=255, width=1, style=Qt.PenStyle.SolidLine):
        """Generate n QPens via sequential colors.

        The colors will be repeated if n is larger than the number of
        pre-defined colors.

        :param int n: number of colors.
        """
        cls._validate_n(n)
        lst = cls.pool * (int(n/len(cls.pool)) + 1)
        for c in lst[:n]:
            pen = QPen(QColor(*c, alpha), width, style)
            pen.setCosmetic(True)
            yield pen

    @classmethod
    def mkBrush(cls, n, *, alpha=255):
        """Generate n QBrushes via sequential colors.

        The colors will be repeated if n is larger than the number of
        pre-defined colors.

        :param int n: number of colors.
        """
        cls._validate_n(n)
        lst = cls.pool * (int(n/len(cls.pool)) + 1)
        for c in lst[:n]:
            yield QBrush(QColor(*c, alpha))


# Valid keys: thermal, flame, yellowy, bipolar, spectrum, cyclic, greyclip, grey
colorMapFactory = \
    {name: ColorMap(*zip(*Gradients[name]["ticks"]))
     for name in Gradients.keys()}


lookupTableFactory = {name: cmap.getLookupTable()
                      for name, cmap in colorMapFactory.items()}


def set_button_color(btn, color: Union[QColor, str]):
    """Set color for a given button."""
    palette = btn.palette()
    if isinstance(color, QColor):
        palette.setColor(QPalette.ColorRole.Button, color)
    else:
        palette.setColor(QPalette.ColorRole.Button, QualitativeColor.mkColor(color))
    btn.setAutoFillBackground(True)
    btn.setPalette(palette)
