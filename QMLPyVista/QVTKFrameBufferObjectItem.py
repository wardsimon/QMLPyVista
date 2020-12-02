import weakref

from PySide2.QtCore import QObject, QUrl, qDebug, qCritical, QEvent, QPointF, Qt, Signal
from PySide2.QtGui import QColor, QMouseEvent, QWheelEvent
from PySide2.QtQuick import QQuickFramebufferObject

from QMLPyVista.QVTKFramebufferObjectRenderer import FboRenderer
from pyvista import BasePlotter, np, try_callback
from functools import wraps, partial
from typing import Any
import vtk


class FboItem(QQuickFramebufferObject, BasePlotter):
    rendererInitialized = Signal()

    def __init__(self, *args, **kwargs):
        qDebug('FboItem::__init__')
        QQuickFramebufferObject.__init__(self)
        self._vtkFboRenderer = None
        BasePlotter.__init__(self, *args, **kwargs)

        self._opts = {
            'border': None,
            'border_color': 'k',
            'border_width': 2.0,
        }
        common_keys = self._opts.keys() & kwargs.keys()
        common_dict = {k: kwargs[k] for k in common_keys}
        self._opts.update(common_dict)

        self.ren_win = vtk.vtkGenericOpenGLRenderWindow = vtk.vtkGenericOpenGLRenderWindow()
        self.iren: vtk.vtkGenericRenderWindowInteractor = vtk.vtkGenericRenderWindowInteractor()
        self.iren.EnableRenderOff()
        self.ren_win.SetInteractor(self.iren)

        self.update_style()

        self.__m_lastMouseLeftButton: QMouseEvent = QMouseEvent(QEvent.Type.None_, QPointF(0, 0), Qt.NoButton,
                                                                Qt.NoButton, Qt.NoModifier)
        self.__m_lastMouseButton: QMouseEvent = QMouseEvent(QEvent.Type.None_, QPointF(0, 0), Qt.NoButton, Qt.NoButton,
                                                            Qt.NoModifier)
        self.__m_lastMouseMove: QMouseEvent = QMouseEvent(QEvent.Type.None_, QPointF(0, 0), Qt.NoButton, Qt.NoButton,
                                                          Qt.NoModifier)
        self.__m_lastMouseWheel: QWheelEvent = None

        self.setMirrorVertically(True)  # QtQuick and OpenGL have opposite Y-Axis directions
        self.setAcceptedMouseButtons(Qt.RightButton | Qt.LeftButton)

    def createRenderer(self):
        qDebug('FboItem::createRenderer')
        renderers = []
        # Create subplot renderers
        row_weights = np.ones(self.shape[0])
        col_weights = np.ones(self.shape[1])

        row_off = np.cumsum(np.abs(row_weights)) / np.sum(np.abs(row_weights))
        row_off = 1 - np.concatenate(([0], row_off))
        col_off = np.cumsum(np.abs(col_weights)) / np.sum(np.abs(col_weights))
        col_off = np.concatenate(([0], col_off))
        idx = 0
        for row in range(self.shape[0]):
            for col in range(self.shape[1]):
                group = self.loc_to_group((row, col))
                nb_rows = None
                nb_cols = None
                if group is not None:
                    if row == self.groups[group, 0] and col == self.groups[group, 1]:
                        # Only add renderer for first location of the group
                        nb_rows = 1 + self.groups[group, 2] - self.groups[group, 0]
                        nb_cols = 1 + self.groups[group, 3] - self.groups[group, 1]
                else:
                    nb_rows = 1
                    nb_cols = 1
                if nb_rows is not None:
                    x0 = col_off[col]
                    y0 = row_off[row + nb_rows]
                    x1 = col_off[col + nb_cols]
                    y1 = row_off[row]
                    if idx == 0:
                        renderer = FboRenderer(self.ren_win, self.iren, **self._opts)
                        renderer.setVtkFboItem(self)
                        mren = renderer.renderer
                        self.ren_win.AddRenderer(mren)
                        self._vtkFboRenderer = renderer
                    else:
                        mren = self._vtkFboRenderer.create_renderer(**self._opts)
                        self.ren_win.AddRenderer(mren)
                    mren.SetViewport(x0, y0, x1, y1)
                    self._render_idxs[row, col] = len(renderers)
                    renderers.append(mren)
                else:
                    self._render_idxs[row, col] = self._render_idxs[self.groups[group, 0], self.groups[group, 1]]
                idx += 1
        self.renderers = renderers
        # create a shadow renderer that lives on top of all others
        qDebug('FboItem::shadowRenderer')
        self._shadow_renderer = self._vtkFboRenderer.create_renderer(**self._opts)
        self._shadow_renderer.SetViewport(0, 0, 1, 1)
        self._shadow_renderer.SetDraw(False)
        self.rendererInitialized.emit()
        return self._vtkFboRenderer

    @property
    def _active_renderer_index(self):
        if self._vtkFboRenderer is None:
            return 0
        return self._vtkFboRenderer.renderer_index

    @_active_renderer_index.setter
    def _active_renderer_index(self, value: int):
        if self._vtkFboRenderer is None:
            return
        self._vtkFboRenderer.renderer_index = value

    @property
    def renderers(self):
        if self._vtkFboRenderer is None:
            return []
        return self._vtkFboRenderer.renderers

    @renderers.setter
    def renderers(self, value):
        if self._vtkFboRenderer is None:
            return
        self._vtkFboRenderer.renderers = value

    @property
    def renderer(self):
        if self._vtkFboRenderer is None:
            return None
        return self._vtkFboRenderer.renderer

    def isInitialized(self) -> bool:
        return isinstance(self.renderers[self._active_renderer_index], FboRenderer)

    # @wraps(BasePlotter.render)
    # def _render(self, *args: Any, **kwargs: Any) -> BasePlotter.render:
    #     """Wrap ``BasePlotter.render``."""
    #     return BasePlotter.render(self, *args, **kwargs)
    #
    # def render(self) -> None:
    #     """Override the ``render`` method to handle threading issues."""
    #     return self.render_signal.emit()

    def set_subplots(self, shape=(1, 1)):
        my_renderers = np.array(self.renderers)
        my_renderers = my_renderers.reshape(self.shape)
        renderers = []

        row_weights = np.ones(shape[0])
        col_weights = np.ones(shape[1])

        row_off = np.cumsum(np.abs(row_weights)) / np.sum(np.abs(row_weights))
        row_off = 1 - np.concatenate(([0], row_off))
        col_off = np.cumsum(np.abs(col_weights)) / np.sum(np.abs(col_weights))
        col_off = np.concatenate(([0], col_off))

        self._render_idxs = np.empty(shape, dtype=int)

        for row in range(shape[0]):
            for col in range(shape[1]):
                group = self.loc_to_group((row, col))
                nb_rows = None
                nb_cols = None
                if group is not None:
                    if row == self.groups[group, 0] and col == self.groups[group, 1]:
                        # Only add renderer for first location of the group
                        nb_rows = 1 + self.groups[group, 2] - self.groups[group, 0]
                        nb_cols = 1 + self.groups[group, 3] - self.groups[group, 1]
                else:
                    nb_rows = 1
                    nb_cols = 1
                if nb_rows is not None:
                    if row >= my_renderers.shape[0] or col >= my_renderers.shape[1]:
                        print('Created another renderer')
                        renderer = self._vtkFboRenderer.create_renderer(**self._opts)
                        self.ren_win.AddRenderer(renderer)
                    else:
                        renderer = my_renderers[row, col]
                    x0 = col_off[col]
                    y0 = row_off[row + nb_rows]
                    x1 = col_off[col + nb_cols]
                    y1 = row_off[row]
                    renderer.SetViewport(x0, y0, x1, y1)
                    self._render_idxs[row, col] = len(renderers)
                    renderers.append(renderer)
                else:
                    self._render_idxs[row, col] = self._render_idxs[self.groups[group, 0], self.groups[group, 1]]
        self.renderers = renderers
        self.shape = (shape[0], shape[1])
        self._background_renderers = [None for _ in range(len(self.renderers))]

    # #* Camera related functions

    def wheelEvent(self, e: QWheelEvent):
        qDebug("myMouseWheel in Item...")
        self.__m_lastMouseWheel = self.__cloneMouseWheelEvent(e)
        self.__m_lastMouseWheel.ignore()
        e.accept()
        self.update()

    def mousePressEvent(self, e: QMouseEvent):
        if e.buttons() & (Qt.RightButton | Qt.LeftButton):
            qDebug("mousePressEvent in Item...")
            self.__m_lastMouseButton = self.__cloneMouseEvent(e)
            self.__m_lastMouseButton.ignore()
            e.accept()
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        qDebug("mouseReleaseEvent in Item...")
        self.__m_lastMouseButton = self.__cloneMouseEvent(e)
        self.__m_lastMouseButton.ignore()
        e.accept()
        self.update()

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() & (Qt.RightButton | Qt.LeftButton):
            qDebug("mouseMoveEvent in Item...")
            self.__m_lastMouseMove = self.__cloneMouseEvent(e)
            self.__m_lastMouseMove.ignore()
            e.accept()
            self.update()

    def getLastMouseButton(self) -> QMouseEvent:
        return self.__m_lastMouseButton

    def getLastMoveEvent(self) -> QMouseEvent:
        return self.__m_lastMouseMove

    def getLastWheelEvent(self) -> QWheelEvent:
        return self.__m_lastMouseWheel

    def __cloneMouseEvent(self, e: QMouseEvent):
        event_type = e.type()
        local_pos = e.localPos()
        button = e.button()
        buttons = e.buttons()
        modifiers = e.modifiers()
        clone = QMouseEvent(event_type, local_pos, button, buttons, modifiers)
        clone.ignore()
        return clone

    def __cloneMouseWheelEvent(self, e: QWheelEvent):
        pos = e.pos()
        globalPos = e.globalPos()
        pixelDelta = e.pixelDelta()
        angleDelta = e.angleDelta()
        buttons = e.buttons()
        modifiers = e.modifiers()
        phase = e.phase()
        inverted = e.inverted()
        clone = QWheelEvent(pos, globalPos, pixelDelta, angleDelta, buttons, modifiers, phase, inverted)
        clone.ignore()
        clone.accepted = False
        return clone

    def update_style(self):
        """Update the camera interactor style."""
        if self._style_class is None:
            # We need an actually custom style to handle button up events
            self._style_class = _style_factory(self._style)(self)
        return self.iren.SetInteractorStyle(self._style_class)

    @property
    def image(self):
        return self._vtkFboRenderer.image()


    # @property
    # def image(self):
    #     """Return an image array of current render window.
    #
    #     To retrieve an image after the render window has been closed,
    #     set: `plotter.store_image = True`
    #     """
    #     if not hasattr(self, 'ren_win') and hasattr(self, 'last_image'):
    #         return self.last_image
    #
    #     width, height = self.window_size
    #
    #     arr = vtk.vtkUnsignedCharArray()
    #     z = vtk.vtkFloatArray()
    #
    #     self.ren_win.GetRGBACharPixelData(0, 0, width - 1, height - 1, 0, arr)
    #     self.ren_win.GetZbufferData(0, 0, width - 1, height - 1, z)
    #     rgba = dsa.vtkDataArrayToVTKArray(arr)
    #     zbuff = dsa.vtkDataArrayToVTKArray(z)
    #
    #     data = np.flipud(rgba.reshape(height, width, -1))
    #     if self.image_transparent_background:
    #         return data
    #     else:  # ignore alpha channel
    #         return data[:, :, :-1]

def _style_factory(klass):
    """Create a subclass with capturing ability, return it."""
    # We have to use a custom subclass for this because the default ones
    # swallow the release events
    # http://vtk.1045678.n5.nabble.com/Mouse-button-release-event-is-still-broken-in-VTK-6-0-0-td5724762.html  # noqa

    class CustomStyle(getattr(vtk, 'vtkInteractorStyle' + klass)):

        def __init__(self, parent):
            super().__init__()
            self._parent = weakref.ref(parent)
            self.AddObserver(
                "LeftButtonPressEvent",
                partial(try_callback, self._press))
            self.AddObserver(
                "LeftButtonReleaseEvent",
                partial(try_callback, self._release))

        def _press(self, obj, event):
            # Figure out which renderer has the event and disable the
            # others
            super().OnLeftButtonDown()
            parent = self._parent()
            if len(parent.renderers) > 0:
                click_pos = parent.iren.GetEventPosition()
                rendererSize = parent.ren_win.GetSize()
                # QT has y flipped, so it's -
                n_rows = len(parent._render_idxs[0])
                n_cols = len(parent._render_idxs)
                click_pos = [n_cols*click_pos[0]/rendererSize[0], -n_rows*click_pos[1]/rendererSize[1]]
                # These are the fractional co-ords. Now we need to set the correct one active....
                # We put renderers in by column and then row [[row], [row]]
                for idx, renderer in enumerate(parent.renderers):
                    cx = np.mod(idx, n_rows) + 1
                    cy = np.floor((idx + 1)/n_cols)
                    xx = np.floor(click_pos[0]/cx).astype(int)
                    yy = np.floor(click_pos[1]/cy).astype(int)
                    interact = renderer.IsInViewport(xx, yy)
                    renderer.SetInteractive(interact)

        def _release(self, obj, event):
            super().OnLeftButtonUp()
            parent = self._parent()
            if len(parent.renderers) > 1:
                for renderer in parent.renderers:
                    renderer.SetInteractive(True)

    return CustomStyle
