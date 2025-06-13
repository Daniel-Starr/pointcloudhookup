import vtk
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import numpy as np

class VTKPointCloudWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.layout.addWidget(self.vtk_widget)

        self.renderer = vtk.vtkRenderer()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self.interactor.Initialize()
        self.interactor.Start()

        self.actors = []

    def clear_scene(self):
        for actor in self.actors:
            self.renderer.RemoveActor(actor)
        self.actors = []

    def create_box_actor(self, center, size, color=(1, 0, 0)):
        cx, cy, cz = center
        dx, dy, dz = size

        points = vtk.vtkPoints()
        for i in range(8):
            x = cx + dx * (0.5 if i & 1 else -0.5)
            y = cy + dy * (0.5 if i & 2 else -0.5)
            z = cz + dz * (0.5 if i & 4 else -0.5)
            points.InsertNextPoint(x, y, z)

        lines = vtk.vtkCellArray()
        edges = [
            (0, 1), (1, 3), (3, 2), (2, 0),
            (4, 5), (5, 7), (7, 6), (6, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        for e in edges:
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, e[0])
            line.GetPointIds().SetId(1, e[1])
            lines.InsertNextCell(line)

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(lines)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(color)
        actor.GetProperty().SetLineWidth(4.0)  # 粗线条
        return actor

    def display_full_scene(self, full_pcd, tower_geometries):
        self.clear_scene()

        # 显示点云（白色点）
        if isinstance(full_pcd, np.ndarray):
            points_np = full_pcd
        else:
            points_np = np.asarray(full_pcd.points)

        if len(points_np) == 0:
            print("⚠️ 点云为空，无法显示")
            return

        vtk_points = vtk.vtkPoints()
        for pt in points_np:
            vtk_points.InsertNextPoint(pt[0], pt[1], pt[2])

        poly_data = vtk.vtkPolyData()
        poly_data.SetPoints(vtk_points)

        vertex_filter = vtk.vtkVertexGlyphFilter()
        vertex_filter.SetInputData(poly_data)
        vertex_filter.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(vertex_filter.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetPointSize(2)
        actor.GetProperty().SetColor(1, 1, 1)  # 白色点云

        self.renderer.AddActor(actor)
        self.actors.append(actor)

        # 处理塔杆几何体
        for geo in tower_geometries:
            if isinstance(geo, vtk.vtkProp):
                self.renderer.AddActor(geo)
                self.actors.append(geo)

            elif isinstance(geo, dict):
                center = geo.get("center") or geo.get("中心坐标")
                size = geo.get("size") or geo.get("尺寸")
                if center is not None and size is not None:
                    actor = self.create_box_actor(center, size, color=(1, 0, 0))
                    self.renderer.AddActor(actor)
                    self.actors.append(actor)
                else:
                    print("⚠️ 跳过缺少几何信息的塔杆：", geo)

            elif isinstance(geo, tuple) and isinstance(geo[0], np.ndarray):
                pts_np, color = geo

                vtk_points = vtk.vtkPoints()
                for pt in pts_np:
                    vtk_points.InsertNextPoint(pt[0], pt[1], pt[2])

                poly_data = vtk.vtkPolyData()
                poly_data.SetPoints(vtk_points)

                # 创建线段
                lines = vtk.vtkCellArray()
                # 每两个点构成一条线
                for i in range(0, len(pts_np), 2):
                    line = vtk.vtkLine()
                    line.GetPointIds().SetId(0, i)
                    line.GetPointIds().SetId(1, i + 1)
                    lines.InsertNextCell(line)

                poly_data.SetLines(lines)

                mapper = vtk.vtkPolyDataMapper()
                mapper.SetInputData(poly_data)

                actor = vtk.vtkActor()
                actor.SetMapper(mapper)
                actor.GetProperty().SetColor(color)
                actor.GetProperty().SetLineWidth(4)  # 加粗线条
                actor.GetProperty().SetLighting(False)  # 关闭光照让线条颜色更纯粹

                self.renderer.AddActor(actor)
                self.actors.append(actor)

            else:
                print(f"⚠️ 非法几何体跳过: {type(geo)} -> {geo}")

        self.renderer.SetBackground(0.0, 0.0, 0.0)
        self.renderer.ResetCamera()

        camera = self.renderer.GetActiveCamera()
        camera.SetViewAngle(30)
        self.renderer.GetRenderWindow().GetInteractor().SetDesiredUpdateRate(1.0)

        self.vtk_widget.GetRenderWindow().Render()
