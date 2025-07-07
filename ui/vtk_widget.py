# 修复后的vtk_widget.py

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

        # 设置背景色
        self.renderer.SetBackground(0.1, 0.1, 0.1)  # 深灰色背景

        self.actors = []

        # 初始化VTK
        self.interactor.Initialize()
        self.vtk_widget.GetRenderWindow().Render()

    def clear_scene(self):
        """清空场景"""
        try:
            for actor in self.actors:
                if actor:
                    self.renderer.RemoveActor(actor)
            self.actors = []
            self.vtk_widget.GetRenderWindow().Render()
        except Exception as e:
            print(f"清空场景失败: {e}")

    def display_full_scene(self, full_pcd, tower_geometries):
        """显示完整场景：点云 + 杆塔"""
        try:
            point_count = len(np.asarray(full_pcd.points)) if full_pcd else 0
            tower_count = len(tower_geometries) if tower_geometries else 0
            print(f"🎬 开始显示场景: 点云={point_count}, 杆塔={tower_count}")

            # 清空现有场景
            self.clear_scene()

            # 1. 显示点云
            if full_pcd is not None:
                points_np = np.asarray(full_pcd.points)
                if len(points_np) > 0:
                    print(f"📊 创建点云演员: {len(points_np)} 个点")
                    point_actor = self.create_point_cloud_actor(points_np)
                    if point_actor:
                        self.renderer.AddActor(point_actor)
                        self.actors.append(point_actor)
                        print("✅ 点云演员添加成功")
                    else:
                        print("❌ 点云演员创建失败")
                else:
                    print("⚠️ 点云为空")
            else:
                print("⚠️ 未提供点云数据")

            # 2. 显示杆塔几何体
            if tower_geometries and len(tower_geometries) > 0:
                print(f"🏗️ 创建杆塔演员: {len(tower_geometries)} 个")
                success_count = 0
                for i, geo in enumerate(tower_geometries):
                    try:
                        tower_actor = self.create_tower_actor(geo, i)
                        if tower_actor:
                            self.renderer.AddActor(tower_actor)
                            self.actors.append(tower_actor)
                            success_count += 1
                        else:
                            print(f"⚠️ 杆塔 {i} 演员创建失败")
                    except Exception as e:
                        print(f"❌ 杆塔 {i} 显示失败: {e}")

                print(f"✅ 成功添加 {success_count}/{len(tower_geometries)} 个杆塔演员")
            else:
                print("📭 无杆塔数据需要显示")

            # 3. 强制渲染更新
            print("🖥️ 开始渲染场景...")
            self.renderer.Modified()  # 标记渲染器已修改

            # 重置相机和渲染
            self.reset_camera_and_render()

            # 确保窗口更新
            self.vtk_widget.update()

            print(f"✅ 场景显示完成 - 总计 {len(self.actors)} 个演员")

        except Exception as e:
            print(f"❌ 显示场景失败: {e}")
            import traceback
            traceback.print_exc()

            # 即使失败也尝试基本渲染
            try:
                self.vtk_widget.GetRenderWindow().Render()
            except:
                pass

    def create_point_cloud_actor(self, points_np):
        """创建点云演员"""
        try:
            # 如果点太多，进行下采样以提高性能
            if len(points_np) > 500000:
                print(f"点云过大({len(points_np)})，进行显示下采样...")
                indices = np.random.choice(len(points_np), 500000, replace=False)
                points_np = points_np[indices]

            # 创建VTK点
            vtk_points = vtk.vtkPoints()
            vtk_points.SetNumberOfPoints(len(points_np))

            for i, point in enumerate(points_np):
                vtk_points.SetPoint(i, point[0], point[1], point[2])

            # 创建多边形数据
            poly_data = vtk.vtkPolyData()
            poly_data.SetPoints(vtk_points)

            # 创建顶点
            vertex_filter = vtk.vtkVertexGlyphFilter()
            vertex_filter.SetInputData(poly_data)
            vertex_filter.Update()

            # 创建映射器
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(vertex_filter.GetOutputPort())

            # 创建演员
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetPointSize(1)  # 点大小
            actor.GetProperty().SetColor(0.8, 0.8, 0.8)  # 浅灰色点云

            return actor

        except Exception as e:
            print(f"创建点云演员失败: {e}")
            return None

    def create_tower_actor(self, geo, index):
        """创建杆塔演员"""
        try:
            if isinstance(geo, tuple) and len(geo) == 2:
                # 线段格式：(点数组, 颜色)
                pts_np, color = geo
                return self.create_line_actor(pts_np, color, index)

            elif isinstance(geo, dict):
                # 字典格式：包含中心坐标和尺寸
                center = geo.get("center") or geo.get("中心坐标")
                size = geo.get("size") or geo.get("尺寸")

                if center and size:
                    return self.create_box_actor(center, size, (1, 0, 0), index)

            else:
                print(f"未知的杆塔几何体格式: {type(geo)}")
                return None

        except Exception as e:
            print(f"创建杆塔演员失败 (索引{index}): {e}")
            return None

    def create_line_actor(self, pts_np, color, index):
        """创建线段演员"""
        try:
            if len(pts_np) == 0:
                return None

            # 创建VTK点
            vtk_points = vtk.vtkPoints()
            for pt in pts_np:
                vtk_points.InsertNextPoint(pt[0], pt[1], pt[2])

            # 创建多边形数据
            poly_data = vtk.vtkPolyData()
            poly_data.SetPoints(vtk_points)

            # 创建线段
            lines = vtk.vtkCellArray()
            # 每两个点构成一条线
            for i in range(0, len(pts_np) - 1, 2):
                if i + 1 < len(pts_np):
                    line = vtk.vtkLine()
                    line.GetPointIds().SetId(0, i)
                    line.GetPointIds().SetId(1, i + 1)
                    lines.InsertNextCell(line)

            poly_data.SetLines(lines)

            # 创建映射器和演员
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(poly_data)

            actor = vtk.vtkActor()
            actor.SetMapper(mapper)

            # 设置颜色
            if isinstance(color, tuple):
                if len(color) == 3:
                    r, g, b = color
                    # 确保颜色值在0-1范围内
                    if all(isinstance(c, int) for c in color):
                        r, g, b = r / 255.0, g / 255.0, b / 255.0
                    actor.GetProperty().SetColor(r, g, b)

            actor.GetProperty().SetLineWidth(3)  # 线条宽度
            actor.GetProperty().SetLighting(False)  # 关闭光照

            print(f"✅ 创建线段演员成功 (杆塔{index})")
            return actor

        except Exception as e:
            print(f"创建线段演员失败: {e}")
            return None

    def create_box_actor(self, center, size, color=(1, 0, 0), index=0):
        """创建盒子演员"""
        try:
            cx, cy, cz = center
            dx, dy, dz = size

            # 创建8个顶点
            points = vtk.vtkPoints()
            vertices = [
                [cx - dx / 2, cy - dy / 2, cz - dz / 2],  # 0
                [cx + dx / 2, cy - dy / 2, cz - dz / 2],  # 1
                [cx + dx / 2, cy + dy / 2, cz - dz / 2],  # 2
                [cx - dx / 2, cy + dy / 2, cz - dz / 2],  # 3
                [cx - dx / 2, cy - dy / 2, cz + dz / 2],  # 4
                [cx + dx / 2, cy - dy / 2, cz + dz / 2],  # 5
                [cx + dx / 2, cy + dy / 2, cz + dz / 2],  # 6
                [cx - dx / 2, cy + dy / 2, cz + dz / 2],  # 7
            ]

            for vertex in vertices:
                points.InsertNextPoint(vertex[0], vertex[1], vertex[2])

            # 创建12条边
            lines = vtk.vtkCellArray()
            edges = [
                (0, 1), (1, 2), (2, 3), (3, 0),  # 底面
                (4, 5), (5, 6), (6, 7), (7, 4),  # 顶面
                (0, 4), (1, 5), (2, 6), (3, 7)  # 竖直边
            ]

            for edge in edges:
                line = vtk.vtkLine()
                line.GetPointIds().SetId(0, edge[0])
                line.GetPointIds().SetId(1, edge[1])
                lines.InsertNextCell(line)

            # 创建多边形数据
            poly_data = vtk.vtkPolyData()
            poly_data.SetPoints(points)
            poly_data.SetLines(lines)

            # 创建映射器和演员
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(poly_data)

            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(color)
            actor.GetProperty().SetLineWidth(4)  # 加粗线条

            print(f"✅ 创建盒子演员成功 (杆塔{index})")
            return actor

        except Exception as e:
            print(f"创建盒子演员失败: {e}")
            return None

    def reset_camera_and_render(self):
        """重置相机并渲染"""
        try:
            # 重置相机以适应所有对象
            self.renderer.ResetCamera()

            # 设置相机参数
            camera = self.renderer.GetActiveCamera()
            camera.SetViewAngle(30)

            # 获取场景边界
            bounds = self.renderer.ComputeVisiblePropBounds()
            if bounds and len(bounds) >= 6:
                # 计算场景中心和大小
                center = [(bounds[1] + bounds[0]) / 2,
                          (bounds[3] + bounds[2]) / 2,
                          (bounds[5] + bounds[4]) / 2]

                diagonal = np.sqrt((bounds[1] - bounds[0]) ** 2 +
                                   (bounds[3] - bounds[2]) ** 2 +
                                   (bounds[5] - bounds[4]) ** 2)

                # 设置相机位置
                camera.SetFocalPoint(center[0], center[1], center[2])
                camera.SetPosition(center[0] + diagonal,
                                   center[1] + diagonal,
                                   center[2] + diagonal / 2)
                camera.SetViewUp(0, 0, 1)

            # 渲染
            self.vtk_widget.GetRenderWindow().Render()
            print("✅ 相机重置和渲染完成")

        except Exception as e:
            print(f"重置相机失败: {e}")
            # 即使失败也尝试基本渲染
            self.vtk_widget.GetRenderWindow().Render()