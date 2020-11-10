__author__ = 'github.com/wardsimon'
__version__ = '0.0.1'

from PySide2.QtCore import QObject, QUrl, qDebug, qCritical, Signal, Property, Slot, Qt
from PySide2.QtQml import QQmlApplicationEngine, qmlRegisterType, QQmlEngine
from PySide2.QtWidgets import QApplication
import PySide2.QtGui as QtGui

import numpy as np

from QMLPyVista.QVTKFrameBufferObjectItem import FboItem

import sys


def defaultFormat(stereo_capable):
    """ Po prostu skopiowałem to z https://github.com/Kitware/VTK/blob/master/GUISupport/Qt/QVTKRenderWindowAdapter.cxx
     i działa poprawnie bufor głębokości
  """
    fmt = QtGui.QSurfaceFormat()
    fmt.setRenderableType(QtGui.QSurfaceFormat.OpenGL)
    fmt.setVersion(3, 2)
    fmt.setProfile(QtGui.QSurfaceFormat.CoreProfile)
    fmt.setSwapBehavior(QtGui.QSurfaceFormat.DoubleBuffer)
    fmt.setRedBufferSize(8)
    fmt.setGreenBufferSize(8)
    fmt.setBlueBufferSize(8)
    fmt.setDepthBufferSize(8)
    fmt.setAlphaBufferSize(8)
    fmt.setStencilBufferSize(0)
    fmt.setStereo(stereo_capable)
    fmt.setSamples(0)

    return fmt


class App(QApplication):

    def __init__(self, sys_argv):
        self._m_vtkFboItem = None
        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
        QtGui.QSurfaceFormat.setDefaultFormat(defaultFormat(False))  # from vtk 8.2.0
        super(App, self).__init__(sys_argv)

    def startApplication(self):
        qDebug('CanvasHandler::startApplication()')
        self._m_vtkFboItem.rendererInitialized.disconnect(self.startApplication)

    def setup(self, engine):
        # Get reference to the QVTKFramebufferObjectItem in QML
        rootObject = engine.rootObjects()[0]  # returns QObject
        self._m_vtkFboItem = rootObject.findChild(FboItem, 'vtkFboItem')

        # Give the vtkFboItem reference to the CanvasHandler
        if (self._m_vtkFboItem):
            qDebug('CanvasHandler::CanvasHandler: setting vtkFboItem to CanvasHandler')
            self._m_vtkFboItem.rendererInitialized.connect(self.startApplication)
        else:
            qCritical('CanvasHandler::CanvasHandler: Unable to get vtkFboItem instance')
            return


class MyExamples:


    def gif(self, fbo):
        import pyvista as pv
        import numpy as np

        x = np.arange(-10, 10, 0.25)
        y = np.arange(-10, 10, 0.25)
        x, y = np.meshgrid(x, y)
        r = np.sqrt(x ** 2 + y ** 2)
        z = np.sin(r)

        # Create and structured surface
        grid = pv.StructuredGrid(x, y, z)

        # Create a plotter object and set the scalars to the Z height
        plotter = fbo
        plotter.add_mesh(grid, scalars=z.ravel(), smooth_shading=True)

        print('Orient the view, then press "q" to close window and produce movie')

        # setup camera and close
        # plotter.show(auto_close=False)

        # Open a gif
        plotter.open_gif("wave.gif")

        pts = grid.points.copy()

        # Update Z and write a frame for each updated position
        nframe = 15
        for phase in np.linspace(0, 2 * np.pi, nframe + 1)[:nframe]:
            z = np.sin(r + phase)
            pts[:, -1] = z.ravel()
            plotter.update_coordinates(pts, render=False)
            plotter.update_scalars(z.ravel(), render=False)

            # must update normals when smooth shading is enabled
            plotter.mesh.compute_normals(cell_normals=False, inplace=True)
            plotter.update()
            plotter.write_frame()  # this will trigger the render

            # otherwise, when not writing frames, render with:
            # plotter.render()

        # Close movie and delete object
        # plotter.close()

    def sphere(self, fbo):
        import vtk
        polyDataSource = vtk.vtkSphereSource()
        polyDataSource.SetRadius(.1)
        res = 100
        polyDataSource.SetPhiResolution(res)
        polyDataSource.SetThetaResolution(res)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(polyDataSource.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor([1, 0, 0])
        fbo.add_actor(actor)
        fbo.update()

    def plane(self, fbo):
        from pyvista import examples

        vol = examples.download_brain()
        fbo.add_mesh_clip_plane(vol)
        fbo.update()

    def extended_line(self, fbo: FboItem):
        import pyvista as pv
        from pyvista import examples
        import numpy as np
        # Extract the data archive and load these files
        # 2D array of XYZ coordinates
        path = examples.download_gpr_path().points
        # 2D array of the data values from the imaging equipment
        data = examples.download_gpr_data_array()


        ###############################################################################

        assert len(path) in data.shape, "Make sure coordinates are present for every trace."
        # If not, you'll need to interpolate the path!

        # Grab the number of samples (in Z dir) and number of traces/soundings
        nsamples, ntraces = data.shape  # Might be opposite for your data, pay attention here

        # Define the Z spacing of your 2D section
        z_spacing = 0.12

        # Create structured points draping down from the path
        points = np.repeat(path, nsamples, axis=0)
        # repeat the Z locations across
        tp = np.arange(0, z_spacing * nsamples, z_spacing)
        tp = path[:, 2][:, None] - tp
        points[:, -1] = tp.ravel()

        ###############################################################################
        # Make a StructuredGrid from the structured points
        grid = pv.StructuredGrid()
        grid.points = points
        grid.dimensions = nsamples, ntraces, 1

        # Add the data array - note the ordering!
        grid["values"] = data.ravel(order="F")

        ###############################################################################
        # And now we can plot it! or process or do anything, because it is a PyVista
        # mesh and the possibilities are endless with PyVista

        cpos = [(1217002.366883762, 345363.80666238244, 3816.828857791056),
                (1216322.4753436751, 344033.0310674846, 3331.052985309526),
                (-0.17716571330686096, -0.25634368781817973, 0.9502106207279767)]
        fbo.add_mesh(grid, cmap="seismic", clim=[-1, 1])
        fbo.add_mesh(pv.PolyData(path), color='orange')
        fbo.set_plot_theme("night")

        fbo.update()

    def cow(self, fbo):
        from pyvista import examples
        # download mesh
        mesh = examples.download_cow()

        decimated = mesh.decimate_boundary(target_reduction=0.75)

        fbo.set_subplots((1, 2))
        fbo.subplot(0, 0)
        fbo.add_text("Original mesh", font_size=24)
        fbo.add_mesh(mesh, show_edges=True, color=True)
        fbo.subplot(0, 1)
        fbo.add_text("Decimated version", font_size=24)
        fbo.add_mesh(decimated, color=True, show_edges=True)

        fbo.link_views()  # link all the views
        # Set a camera position to all linked views
        fbo.camera_position = [(15, 5, 0), (0, 0, 0), (0, 1, 0)]

        fbo.update()
        fbo.open_gif("linked.gif")

        # Update camera and write a frame for each updated position
        nframe = 15
        for i in range(nframe):
            fbo.camera_position = [
                (15 * np.cos(i * np.pi / 45.0), 5.0, 15 * np.sin(i * np.pi / 45.0)),
                (0, 0, 0),
                (0, 1, 0),
            ]
            fbo.update()
            fbo.write_frame()


class canvasHandler(QObject):

    def __init__(self, parent=None):
        super(canvasHandler, self).__init__(parent=parent)
        self.fbo = None
        self.examples = MyExamples()

    @Slot()
    def plot_example(self):
        self.examples.cow(self.fbo)

    @Slot(int, int, int)
    def mousePressEvent(self, button: int, screenX: int, screenY: int):
        qDebug('CanvasHandler::mousePressEvent()')
        # self._m_vtkFboItem.selectModel(screenX, screenY)

    @Slot(int, int, int)
    def mouseMoveEvent(self, button: int, screenX: int, screenY: int):
        qDebug('CanvasHandler::mouseMoveEvent()')

    @Slot(int, int, int)
    def mouseReleaseEvent(self, button: int, screenX: int, screenY: int):
        qDebug('CanvasHandler::mouseReleaseEvent()')


def main():
    app = App(sys.argv)
    engine = QQmlApplicationEngine()

    app.setApplicationName('QtVTK-Py')

    qmlRegisterType(FboItem, 'QtVTK', 1, 0, 'VtkFboItem')

    handler = canvasHandler()

    # Expose/Bind Python classes (QObject) to QML
    ctxt = engine.rootContext()  # returns QQmlContext
    ctxt.setContextProperty('canvasHandler', handler)

    # Load main QML file
    engine.load(QUrl.fromLocalFile('examples/main7.qml'))

    app.setup(engine)
    handler.fbo = app._m_vtkFboItem

    rc = app.exec_()
    qDebug(f'CanvasHandler::CanvasHandler: Execution finished with return code: {rc}')


if __name__ == '__main__':
    main()
