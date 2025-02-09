# -*- coding: utf-8 -*-
"""
PyQtGraph - Scientific Graphics and GUI Library for Python
www.pyqtgraph.org
"""

__version__ = '0.11.0.dev0'

import os, sys

CONFIG_OPTIONS = {
    'leftButtonPan': True,  ## if false, left button drags a rubber band for zooming in viewbox
    # foreground/background take any arguments to the 'mkColor' in /pyqtgraph/functions.py
    'foreground': 'd',  ## default foreground color for axes, labels, etc.
    'background': 'k',        ## default background for GraphicsWidget
    'antialias': False,
    'editorCommand': None,  ## command used to invoke code editor from ConsoleWidgets
    'useWeave': False,       ## Use weave to speed up some operations, if it is available
    'weaveDebug': False,    ## Print full error message if weave compile fails
    'exitCleanup': True,    ## Attempt to work around some exit crash bugs in PyQt and PySide
    'enableExperimental': False, ## Enable experimental features (the curious can search for this key in the code)
    'crashWarning': False,  # If True, print warnings about situations that may result in a crash
    'imageAxisOrder': 'col-major',  # For 'row-major', image data is expected in the standard (row, col) order.
                                 # For 'col-major', image data is expected in reversed (col, row) order.
                                 # The default is 'col-major' for backward compatibility, but this may
                                 # change in the future.
} 


def setConfigOption(opt, value):
    if opt not in CONFIG_OPTIONS:
        raise KeyError('Unknown configuration option "%s"' % opt)
    if opt == 'imageAxisOrder' and value not in ('row-major', 'col-major'):
        raise ValueError('imageAxisOrder must be either "row-major" or "col-major"')
    CONFIG_OPTIONS[opt] = value

def setConfigOptions(**opts):
    """Set global configuration options. 
    
    Each keyword argument sets one global option. 
    """
    for k,v in opts.items():
        setConfigOption(k, v)

def getConfigOption(opt):
    """Return the value of a single global configuration option.
    """
    return CONFIG_OPTIONS[opt]


def systemInfo():
    print("sys.platform: %s" % sys.platform)
    print("sys.version: %s" % sys.version)
    from .Qt import VERSION_INFO
    print("qt bindings: %s" % VERSION_INFO)
    
    global __version__
    rev = None
    if __version__ is None:  ## this code was probably checked out from bzr; look up the last-revision file
        lastRevFile = os.path.join(os.path.dirname(__file__), '..', '.bzr', 'branch', 'last-revision')
        if os.path.exists(lastRevFile):
            with open(lastRevFile, 'r') as fd:
                rev = fd.read().strip()
    
    print("pyqtgraph: %s; %s" % (__version__, rev))
    print("config:")
    import pprint
    pprint.pprint(CONFIG_OPTIONS)

## Rename orphaned .pyc files. This is *probably* safe :)
## We only do this if __version__ is None, indicating the code was probably pulled
## from the repository. 
def renamePyc(startDir):
    ### Used to rename orphaned .pyc files
    ### When a python file changes its location in the repository, usually the .pyc file
    ### is left behind, possibly causing mysterious and difficult to track bugs. 

    ### Note that this is no longer necessary for python 3.2; from PEP 3147:
    ### "If the py source file is missing, the pyc file inside __pycache__ will be ignored. 
    ### This eliminates the problem of accidental stale pyc file imports."
    
    printed = False
    startDir = os.path.abspath(startDir)
    for path, dirs, files in os.walk(startDir):
        if '__pycache__' in path:
            continue
        for f in files:
            fileName = os.path.join(path, f)
            base, ext = os.path.splitext(fileName)
            py = base + ".py"
            if ext == '.pyc' and not os.path.isfile(py):
                if not printed:
                    print("NOTE: Renaming orphaned .pyc files:")
                    printed = True
                n = 1
                while True:
                    name2 = fileName + ".renamed%d" % n
                    if not os.path.exists(name2):
                        break
                    n += 1
                print("  " + fileName + "  ==>")
                print("  " + name2)
                os.rename(fileName, name2)
                
path = os.path.split(__file__)[0]
if __version__ is None and not hasattr(sys, 'frozen') and sys.version_info[0] == 2: ## If we are frozen, there's a good chance we don't have the original .py files anymore.
    renamePyc(path)

from .graphicsItems.GraphicsWidget import *
from .graphicsItems.TextItem import *
from .graphicsItems.UIGraphicsItem import *
from .graphicsItems.GraphicsObject import *
from .graphicsItems.ROI import *
from .graphicsItems.InfiniteLine import *
from .graphicsItems.GraphicsItem import *
from .graphicsItems.ViewBox import *
from .graphicsItems.ArrowItem import *
from .graphicsItems.AxisItem import *
from .graphicsItems.LabelItem import *
from .graphicsItems.GraphicsWidgetAnchor import *
from .graphicsItems.GradientEditorItem import *
from .graphicsItems.LinearRegionItem import *
from .graphicsItems.LegendItem import *
from .graphicsItems.ItemGroup import *

from .widgets.SpinBox import *
from .widgets.GraphicsView import *

from .WidgetGroup import *
from .Point import Point
from .SRTTransform import SRTTransform
from .functions import *
from .SignalProxy import *
from .colormap import *
from .ptime import time
from .Qt import isQObjectAlive


##############################################################
## PyQt and PySide both are prone to crashing on exit. 
## There are two general approaches to dealing with this:
##  1. Install atexit handlers that assist in tearing down to avoid crashes.
##     This helps, but is never perfect.
##  2. Terminate the process before python starts tearing down
##     This is potentially dangerous

## Attempts to work around exit crashes:
import atexit
_cleanupCalled = False
def cleanup():
    global _cleanupCalled
    if _cleanupCalled:
        return
    
    if not getConfigOption('exitCleanup'):
        return
    
    ViewBox.quit()  ## tell ViewBox that it doesn't need to deregister views anymore.
    
    ## Workaround for Qt exit crash:
    ## ALL QGraphicsItems must have a scene before they are deleted.
    ## This is potentially very expensive, but preferred over crashing.
    ## Note: this appears to be fixed in PySide as of 2012.12, but it should be left in for a while longer..
    app = QtGui.QApplication.instance()
    if app is None or not isinstance(app, QtGui.QApplication):
        # app was never constructed is already deleted or is an
        # QCoreApplication/QGuiApplication and not a full QApplication
        return
    import gc
    s = QtGui.QGraphicsScene()
    for o in gc.get_objects():
        try:
            if isinstance(o, QtGui.QGraphicsItem) and isQObjectAlive(o) and o.scene() is None:
                if getConfigOption('crashWarning'):
                    sys.stderr.write('Error: graphics item without scene. '
                        'Make sure ViewBox.close() and GraphicsView.close() '
                        'are properly called before app shutdown (%s)\n' % (o,))
                
                s.addItem(o)
        except (RuntimeError, ReferenceError):  ## occurs if a python wrapper no longer has its underlying C++ object
            continue
    _cleanupCalled = True

atexit.register(cleanup)

# Call cleanup when QApplication quits. This is necessary because sometimes
# the QApplication will quit before the atexit callbacks are invoked.
# Note: cannot connect this function until QApplication has been created, so
# instead we have GraphicsView.__init__ call this for us.
_cleanupConnected = False
def _connectCleanup():
    global _cleanupConnected
    if _cleanupConnected:
        return
    QtGui.QApplication.instance().aboutToQuit.connect(cleanup)
    _cleanupConnected = True


## Optional function for exiting immediately (with some manual teardown)
def exit():
    """
    Causes python to exit without garbage-collecting any objects, and thus avoids
    calling object destructor methods. This is a sledgehammer workaround for 
    a variety of bugs in PyQt and Pyside that cause crashes on exit.
    
    This function does the following in an attempt to 'safely' terminate
    the process:
    
    * Invoke atexit callbacks
    * Close all open file handles
    * os._exit()
    
    Note: there is some potential for causing damage with this function if you
    are using objects that _require_ their destructors to be called (for example,
    to properly terminate log files, disconnect from devices, etc). Situations
    like this are probably quite rare, but use at your own risk.
    """
    
    ## first disable our own cleanup function; won't be needing it.
    setConfigOptions(exitCleanup=False)
    
    ## invoke atexit callbacks
    atexit._run_exitfuncs()
    
    ## close file handles
    if sys.platform == 'darwin':
        for fd in range(3, 4096):
            if fd in [7]:  # trying to close 7 produces an illegal instruction on the Mac.
                continue
            try:
                os.close(fd)
            except OSError:
                pass
    else:
        os.closerange(3, 4096) ## just guessing on the maximum descriptor count..

    os._exit(0)
