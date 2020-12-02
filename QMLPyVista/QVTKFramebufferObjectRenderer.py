import random
from functools import wraps
from typing import Any, List

from PySide2.QtCore import QObject, QUrl, qDebug, qCritical, QFileInfo, QEvent, Qt, QSize, Signal
from PySide2.QtGui import QSurfaceFormat, QColor, QMouseEvent, QWheelEvent, QOpenGLFramebufferObject, \
    QOpenGLFramebufferObjectFormat, QOpenGLFunctions
from PySide2.QtQuick import QQuickFramebufferObject
import collections.abc

import vtk
from pyvista import parse_color, rcParams
from pyvista.plotting.renderer import Renderer, _remove_mapper_from_plotter
from weakref import proxy

from vtkmodules.util.numpy_support import vtk_to_numpy


class FboRenderer(QObject, QQuickFramebufferObject.Renderer):

    render_signal = Signal()
    dump_ren_win = Signal()

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
        self._renderer = [RendererOPENGL(parent=self, **kwargs)]
        self._renderer[0].AutomaticLightCreationOn()
        self._renderer_index = 0

        self._render_window = render_window
        self._render_window.OpenGLInitContext()
        self._interactor = interactor

        self.render_signal.connect(self._render)
        self.dump_ren_win.connect(self._dump_ren_win)
        self.__m_vtkFboItem = None
        self.__image_data = None

    @property
    def _scalar_bar_mappers(self):
        if self.__m_vtkFboItem is not None:
            return self.__m_vtkFboItem._scalar_bar_mappers

    @_scalar_bar_mappers.setter
    def _scalar_bar_mappers(self, value):
        if self.__m_vtkFboItem is not None:
            self.__m_vtkFboItem._scalar_bar_mappers = value

    @property
    def _scalar_bar_ranges(self):
        if self.__m_vtkFboItem is not None:
            return self.__m_vtkFboItem._scalar_bar_ranges

    @_scalar_bar_ranges.setter
    def _scalar_bar_ranges(self, value):
        if self.__m_vtkFboItem is not None:
            self.__m_vtkFboItem._scalar_bar_ranges = value

    @property
    def remove_actor(self):
        if self.__m_vtkFboItem is not None:
            return self.__m_vtkFboItem.remove_actor

    @property
    def _scalar_bar_slot_lookup(self):
        if self.__m_vtkFboItem is not None:
            return self.__m_vtkFboItem._scalar_bar_slot_lookup

    @_scalar_bar_slot_lookup.setter
    def _scalar_bar_slot_lookup(self, value):
        if self.__m_vtkFboItem is not None:
            self.__m_vtkFboItem._scalar_bar_slot_lookup = value

    @property
    def _scalar_bar_slots(self):
        if self.__m_vtkFboItem is not None:
            return self.__m_vtkFboItem._scalar_bar_slots

    @_scalar_bar_slots.setter
    def _scalar_bar_slots(self, value):
        if self.__m_vtkFboItem is not None:
            self.__m_vtkFboItem._scalar_bar_slots = value

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
        return RendererOPENGL(parent=self, **kwargs)

    def setVtkFboItem(self, vtkFboItem):
        self.__m_vtkFboItem = vtkFboItem

    def _render(self, *args: Any, **kwargs: Any):
        """Wrap ``BasePlotter.render``."""
        return FboRenderer.render_this_thread(self, *args, **kwargs)

    def _dump_ren_win(self, *args, **kwargs):
        return FboRenderer._dump_ren_win(self, *args, **kwargs)

    def render(self) -> None:
        """Override the ``render`` method to handle threading issues."""
        return self.render_signal.emit()

    def image(self):
        return self.dump_ren_win.emit()

    @property
    def iren(self):
        return self._interactor

    def render_this_thread(self):
        qDebug('ObjectRenderer: RENDER')
        self._render_window.PushState()
        self.openGLInitState()
        self._render_window.Start()

        # * Process camera related commands
        if self.__m_mouseEvent and not self.__m_mouseEvent.isAccepted():
            # qDebug('A')
            self._interactor.SetEventInformationFlipY(
                self.__m_mouseEvent.x(), self.__m_mouseEvent.y(),
                1 if (self.__m_mouseEvent.modifiers() & Qt.ControlModifier) > 0 else 0,
                1 if (self.__m_mouseEvent.modifiers() & Qt.ShiftModifier) > 0 else 0,
                '0',
                1 if self.__m_mouseEvent.type() == QEvent.MouseButtonDblClick else 0
            )

            if self.__m_mouseEvent.type() == QEvent.MouseButtonPress:
                # qDebug('B')
                self._interactor.InvokeEvent(vtk.vtkCommand.LeftButtonPressEvent)
            elif self.__m_mouseEvent.type() == QEvent.MouseButtonRelease:
                # qDebug('C')
                self._interactor.InvokeEvent(vtk.vtkCommand.LeftButtonReleaseEvent)

            self.__m_mouseEvent.accept()

        # * Process move event
        if self.__m_moveEvent and not self.__m_moveEvent.isAccepted():
            # qDebug('D')
            if self.__m_moveEvent.type() == QEvent.MouseMove and self.__m_moveEvent.buttons() & (
                    Qt.RightButton | Qt.LeftButton):
                # qDebug('E')
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
            # qDebug('F')
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

    def _dump_ren_win(self):
        qDebug('ObjectRenderer: DUMPING RENDER')
        self._render_window.PushState()
        self.openGLInitState()
        self._render_window.Start()
        # Render
        self._render_window.Render()

        width, height = self._render_window.GetSize()
        arr = vtk.vtkUnsignedCharArray()
        self.ren_win.GetRGBACharPixelData(0, 0, width - 1, height - 1, 0, arr)
        data = vtk_to_numpy(arr).reshape(height, width, -1)[::-1]
        self._render_window.PopState()
        self.__m_vtkFboItem.window().resetOpenGLState()
        return data

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


class RendererOPENGL(Renderer):

    def __init__(self, *args, **kwargs):
        super(RendererOPENGL, self).__init__(*args, **kwargs)


    def add_actor(self, uinput, reset_camera=False, name=None, culling=False,
                  pickable=True, render=True):
        """Add an actor to render window.
        Creates an actor if input is a mapper.
        Parameters
        ----------
        uinput : vtk.vtkMapper or vtk.vtkActor
            vtk mapper or vtk actor to be added.
        reset_camera : bool, optional
            Resets the camera when true.
        culling : str, optional
            Does not render faces that are culled. Options are ``'front'`` or
            ``'back'``. This can be helpful for dense surface meshes,
            especially when edges are visible, but can cause flat
            meshes to be partially displayed.  Default False.
        Return
        ------
        actor : vtk.vtkActor
            The actor.
        actor_properties : vtk.Properties
            Actor properties.
        """
        # Remove actor by that name if present
        rv = self.remove_actor(name, reset_camera=False, render=render)

        if isinstance(uinput, vtk.vtkMapper):
            actor = vtk.vtkActor()
            actor.SetMapper(uinput)
        else:
            actor = uinput

        self.AddActor(actor)
        actor.renderer = proxy(self)

        if name is None:
            name = actor.GetAddressAsString("")

        self._actors[name] = actor

        if reset_camera:
            self.reset_camera(render)
        elif not self.camera_set and reset_camera is None and not rv:
            self.reset_camera(render)
        elif render:
            self.parent.render()

        self.update_bounds_axes()

        if isinstance(culling, str):
            culling = culling.lower()

        if culling:
            if culling in [True, 'back', 'backface', 'b']:
                try:
                    actor.GetProperty().BackfaceCullingOn()
                except AttributeError:  # pragma: no cover
                    pass
            elif culling in ['front', 'frontface', 'f']:
                try:
                    actor.GetProperty().FrontfaceCullingOn()
                except AttributeError:  # pragma: no cover
                    pass
            else:
                raise ValueError(f'Culling option ({culling}) not understood.')

        actor.SetPickable(pickable)

        self.ResetCameraClippingRange()
        if render:
            self.Modified()

        return actor, actor.GetProperty()

    def remove_actor(self, actor, reset_camera=False, render=True):
        """Remove an actor from the Renderer.
        Parameters
        ----------
        actor : str, vtk.vtkActor, list or tuple
            If the type is ``str``, removes the previously added actor with
            the given name. If the type is ``vtk.vtkActor``, removes the actor
            if it's previously added to the Renderer. If ``list`` or ``tuple``,
            removes iteratively each actor.
        reset_camera : bool, optional
            Resets camera so all actors can be seen.
        render : bool, optional
            Render upon actor removal.  Set this to ``False`` to stop
            the render window from rendering when an actor is removed.
        Return
        ------
        success : bool
            True when actor removed.  False when actor has not been
            removed.
        """
        name = None
        if isinstance(actor, str):
            name = actor
            keys = list(self._actors.keys())
            names = []
            for k in keys:
                if k.startswith(f'{name}-'):
                    names.append(k)
            if len(names) > 0:
                self.remove_actor(names, reset_camera=reset_camera, render=render)
            try:
                actor = self._actors[name]
            except KeyError:
                # If actor of that name is not present then return success
                return False
        if isinstance(actor, collections.abc.Iterable):
            success = False
            for a in actor:
                rv = self.remove_actor(a, reset_camera=reset_camera, render=render)
                if rv or success:
                    success = True
            return success
        if actor is None:
            return False

        # First remove this actor's mapper from _scalar_bar_mappers
        _remove_mapper_from_plotter(self.parent, actor, False, render=render)
        self.RemoveActor(actor)

        if name is None:
            for k, v in self._actors.items():
                if v == actor:
                    name = k
        self._actors.pop(name, None)
        self.update_bounds_axes()
        if reset_camera:
            self.reset_camera()
        elif not self.camera_set and reset_camera is None:
            self.reset_camera()
        elif render:
            self.parent.render()
            self.Modified()
        return True

    def set_background(self, color, top=None):
        """Set the background color.
        Parameters
        ----------
        color : string or 3 item list, optional, defaults to white
            Either a string, rgb list, or hex color string.  For example:
                color='white'
                color='w'
                color=[1, 1, 1]
                color='#FFFFFF'
        top : string or 3 item list, optional, defaults to None
            If given, this will enable a gradient background where the
            ``color`` argument is at the bottom and the color given in ``top``
            will be the color at the top of the renderer.
        """
        if color is None:
            color = rcParams['background']

        use_gradient = False
        if top is not None:
            use_gradient = True
        c = parse_color(color)
        self.SetBackground(c)
        if use_gradient:
            self.GradientBackgroundOn()
            self.SetBackground2(parse_color(top))
        else:
            self.GradientBackgroundOff()
        self.Modified()