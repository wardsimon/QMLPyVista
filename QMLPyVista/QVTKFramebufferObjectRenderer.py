import random
from functools import wraps
from typing import Any, List

from PySide2.QtCore import QObject, QUrl, qDebug, qCritical, QFileInfo, QEvent, Qt, QSize, Signal
from PySide2.QtGui import QSurfaceFormat, QColor, QMouseEvent, QWheelEvent, QOpenGLFramebufferObject, \
    QOpenGLFramebufferObjectFormat, QOpenGLFunctions
from PySide2.QtQuick import QQuickFramebufferObject

import vtk
from pyvista.plotting.renderer import Renderer


class FboRenderer(QObject, QQuickFramebufferObject.Renderer):

    render_signal = Signal()

    def __init__(self, render_window, interactor, *args, **kwargs):
        self.gl = QOpenGLFunctions()
        QQuickFramebufferObject.Renderer.__init__(self)
        QObject.__init__(self)
        self.__fbo = None

        self.__m_mouseLeftButton: QMouseEvent = None
        self.__m_mouseEvent: QMouseEvent = None
        self.__m_moveEvent: QMouseEvent = None
        self.__m_wheelEvent: QWheelEvent = None

        self.__m_firstRender: bool = True

        # self._render_window: vtk.vtkGenericOpenGLRenderWindow = vtk.vtkGenericOpenGLRenderWindow()
        self._renderer = [Renderer(parent=self, **kwargs)]
        self._renderer_index = 0

        self._render_window = render_window
        self._render_window.OpenGLInitContext()
        self._interactor = interactor

        self.render_signal.connect(self._render)
        self.__m_vtkFboItem = None

    @property
    def renderers(self) -> List[Renderer]:
        return self._renderer

    @renderers.setter
    def renderers(self, value: List[Renderer]):
        self._renderer = value

    @property
    def renderer_index(self) -> int:
        return self._renderer_index

    @renderer_index.setter
    def renderer_index(self, value: int):
        self._renderer_index = value

    @property
    def renderer(self) -> Renderer:
        return self._renderer[self.renderer_index]

    def create_renderer(self, *args, **kwargs) -> Renderer:
        return Renderer(parent=self, **kwargs)

    def setVtkFboItem(self, vtkFboItem):
        self.__m_vtkFboItem = vtkFboItem

    def _render(self, *args: Any, **kwargs: Any):
        """Wrap ``BasePlotter.render``."""
        return FboRenderer.render_this_thread(self, *args, **kwargs)

    def render(self) -> None:
        """Override the ``render`` method to handle threading issues."""
        return self.render_signal.emit()

    def render_this_thread(self):
        qDebug('ObjectRenderer: RENDER')
        self._render_window.PushState()
        self.openGLInitState()
        self._render_window.Start()

        # * Process camera related commands
        if self.__m_mouseEvent and not self.__m_mouseEvent.isAccepted():
            self._interactor.SetEventInformationFlipY(
                self.__m_mouseEvent.x(), self.__m_mouseEvent.y(),
                1 if (self.__m_mouseEvent.modifiers() & Qt.ControlModifier) > 0 else 0,
                1 if (self.__m_mouseEvent.modifiers() & Qt.ShiftModifier) > 0 else 0,
                '0',
                1 if self.__m_mouseEvent.type() == QEvent.MouseButtonDblClick else 0
            )

            if self.__m_mouseEvent.type() == QEvent.MouseButtonPress:
                self._interactor.InvokeEvent(vtk.vtkCommand.LeftButtonPressEvent)
            elif self.__m_mouseEvent.type() == QEvent.MouseButtonRelease:
                self._interactor.InvokeEvent(vtk.vtkCommand.LeftButtonReleaseEvent)

            self.__m_mouseEvent.accept()

        # * Process move event
        if self.__m_moveEvent and not self.__m_moveEvent.isAccepted():
            if self.__m_moveEvent.type() == QEvent.MouseMove and self.__m_moveEvent.buttons() & (
                    Qt.RightButton | Qt.LeftButton):
                self._interactor.SetEventInformationFlipY(
                    self.__m_moveEvent.x(),
                    self.__m_moveEvent.y(),
                    1 if (self.__m_moveEvent.modifiers() & Qt.ControlModifier) > 0 else 0,
                    1 if (self.__m_moveEvent.modifiers() & Qt.ShiftModifier) > 0 else 0,
                    '0',
                    1 if self.__m_moveEvent.type() == QEvent.MouseButtonDblClick else 0
                )

                self._interactor.InvokeEvent(vtk.vtkCommand.MouseMoveEvent)

            self.__m_moveEvent.accept()

        # * Process wheel event
        if self.__m_wheelEvent and not self.__m_wheelEvent.isAccepted():
            self._interactor.SetEventInformationFlipY(
                self.__m_wheelEvent.x(), self.__m_wheelEvent.y(),
                1 if (self.__m_wheelEvent.modifiers() & Qt.ControlModifier) > 0 else 0,
                1 if (self.__m_wheelEvent.modifiers() & Qt.ShiftModifier) > 0 else 0,
                '0',
                1 if self.__m_wheelEvent.type() == QEvent.MouseButtonDblClick else 0
            )

            if self.__m_wheelEvent.delta() > 0:
                self._interactor.InvokeEvent(vtk.vtkCommand.MouseWheelForwardEvent)
            elif self.__m_wheelEvent.delta() < 0:
                self._interactor.InvokeEvent(vtk.vtkCommand.MouseWheelBackwardEvent)

            self.__m_wheelEvent.accept()

        # Render
        self._render_window.Render()
        self._render_window.PopState()
        self.__m_vtkFboItem.window().resetOpenGLState()

    def synchronize(self, item: QQuickFramebufferObject):
        qDebug('ObjectRenderer: SYNC')
        rendererSize = self._render_window.GetSize()
        if self.__m_vtkFboItem.width() != rendererSize[0] or self.__m_vtkFboItem.height() != rendererSize[1]:
            self._render_window.SetSize(int(self.__m_vtkFboItem.width()), int(self.__m_vtkFboItem.height()))

        # * Copy mouse events
        print(self.__m_vtkFboItem.getLastMouseButton().isAccepted())
        if not self.__m_vtkFboItem.getLastMouseButton().isAccepted():
            self.__m_mouseEvent = self.__m_vtkFboItem.getLastMouseButton()

        if not self.__m_vtkFboItem.getLastMoveEvent().isAccepted():
            self.__m_moveEvent = self.__m_vtkFboItem.getLastMoveEvent()

        if self.__m_vtkFboItem.getLastWheelEvent() and not self.__m_vtkFboItem.getLastWheelEvent().isAccepted():
            self.__m_wheelEvent = self.__m_vtkFboItem.getLastWheelEvent()

    def createFramebufferObject(self, size):
        qDebug('ObjectRenderer: Created OpenGLFBO')
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.Depth)
        fbo = QOpenGLFramebufferObject(size, fmt)
        fbo.release()
        self.__fbo = fbo
        return self.__fbo

    def openGLInitState(self):
        self._render_window.OpenGLInitState()
        self._render_window.MakeCurrent()
        # When called from a pyvista function this fails....
        self.gl.initializeOpenGLFunctions()

    # Not really needed
    def resetCamera(self):
        # * Setting the clipping range here messes with the opacity of the actors prior to moving the camera
        m_camPositionX = -10
        m_camPositionY = -20
        m_camPositionZ = 10
        self._renderer.GetActiveCamera().SetPosition(m_camPositionX, m_camPositionY, m_camPositionZ)
        self._renderer.GetActiveCamera().SetFocalPoint(0.0, 0.0, 0.0)
        self._renderer.GetActiveCamera().SetViewUp(0.0, 0.0, 1.0)
        self._renderer.ResetCameraClippingRange()
