import sys
import os
import threading
import numpy as np
import laspy
import open3d as o3d

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar,
    QTextEdit, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject

from ui.import_PC import run_voxel_downsampling
from ui.vtk_widget import VTKPointCloudWidget
from ui.compress import GIMExtractor
from ui.parsetower import GIMTower
from ui.review_panel import build_review_widget
from ui.save_cbm import update_and_compress_from_correction
from ui.extract import extract_and_visualize_towers  # 导入extract.py

from utils.table_match_gim import match_from_gim_tower_list
from utils.table_match_gim import correct_from_gim_tower_list
from utils.tower_extraction import extract_towers


class ProgressSignal(QObject):
    update_progress = pyqtSignal(int)
    append_log = pyqtSignal(str)
    update_vtk_scene = pyqtSignal(object, object)
    update_table = pyqtSignal(list)
    switch_to_table = pyqtSignal()
    switch_to_vtk = pyqtSignal()


class TowerDetectionTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("竣工图模型与激光点云数据自动校对与优化工具")
        self.setGeometry(300, 100, 1400, 800)

        # 信号对象
        self.signals = ProgressSignal()

        # 连接信号槽
        self.signals.update_progress.connect(self.progress_bar_update)
        self.signals.append_log.connect(self.log_output_append)
        self.signals.update_vtk_scene.connect(self.vtk_view_display_safe)
        self.signals.update_table.connect(self.fill_gim_table)
        self.signals.switch_to_table.connect(self.show_table_view)
        self.signals.switch_to_vtk.connect(self.show_vtk_view)

        self.view_history = []
        self.init_ui()

        # 初始化数据存储变量
        self.pointcloud_path = None
        self.downsampled_pcd = None
        self.original_pcd = None
        self.tower_list = []
        self.gim_path = None
        self.cbm_filenames = []
        self.tower_geometries = []
        self.original_gim_file_path = None
        self.corrected_data = None
        self.tower_obbs = []  # 存储提取的杆塔OBB信息

    def init_ui(self):
        button_layout = QHBoxLayout()
        self.buttons = {}
        for name in ["导入GIM", "导入点云", "去除地物", "提取杆塔", "匹配", "校对", "保存", "返回"]:
            btn = QPushButton(name)
            button_layout.addWidget(btn)
            self.buttons[name] = btn
        button_layout.addStretch()

        left_widget = QWidget()
        left_layout = QVBoxLayout()
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("font-size: 12px;")
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        left_layout.addWidget(log_group, 10)
        left_widget.setLayout(left_layout)

        self.right_stack = QStackedWidget()
        self.vtk_view = VTKPointCloudWidget()
        self.gim_table = QTableWidget()
        self.review_panel = QWidget()
        self.review_panel.setLayout(QHBoxLayout())

        self.right_stack.addWidget(self.vtk_view)
        self.right_stack.addWidget(self.gim_table)
        self.right_stack.addWidget(self.review_panel)

        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.right_stack)
        right_widget.setLayout(right_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 1150])

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        main_layout = QVBoxLayout()
        main_layout.addLayout(button_layout)
        main_layout.addWidget(splitter)
        main_layout.addWidget(self.progress_bar)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.buttons["导入点云"].clicked.connect(self.import_pointcloud)
        self.buttons["去除地物"].clicked.connect(self.remove_ground_objects)
        self.buttons["提取杆塔"].clicked.connect(self.extract_tower)
        self.buttons["导入GIM"].clicked.connect(self.import_gim_file_threaded)
        self.buttons["匹配"].clicked.connect(self.match_only)
        self.buttons["校对"].clicked.connect(self.correct_only)
        self.buttons["保存"].clicked.connect(self.save_and_compress)
        self.buttons["返回"].clicked.connect(self.go_back_view)

    def push_view_history(self):
        self.view_history.append(self.right_stack.currentIndex())

    def go_back_view(self):
        if self.view_history:
            last_index = self.view_history.pop()
            self.right_stack.setCurrentIndex(last_index)

    def show_table_view(self):
        self.push_view_history()
        self.right_stack.setCurrentIndex(1)

    def import_pointcloud(self):
        """导入点云 - 自动显示版本"""
        file_path, _ = QFileDialog.getOpenFileName(self, "导入点云", "", "LAS Files (*.las *.laz);;All Files (*)")
        if file_path:
            self.pointcloud_path = file_path
            self.progress_bar.setValue(0)
            self.log_output.append("✅ 点云数据导入成功")

            # 自动切换到VTK视图
            self.push_view_history()
            self.right_stack.setCurrentIndex(0)

            # 清空之前的杆塔数据
            self.tower_geometries = []
            self.tower_obbs = []

            # 在后台线程中加载和显示点云
            threading.Thread(target=self.load_and_display_pointcloud, args=(file_path,), daemon=True).start()

    def load_and_display_pointcloud(self, file_path):
        """加载并显示点云"""
        try:
            self.signals.append_log.emit("📂 正在加载点云文件...")
            self.signals.update_progress.emit(10)

            # 加载点云
            las = laspy.read(file_path)
            xyz = np.vstack((las.x, las.y, las.z)).T

            # 如果点云太大，先下采样用于预览
            if len(xyz) > 200000:
                self.signals.append_log.emit("📉 点云较大，进行预览下采样...")
                indices = np.random.choice(len(xyz), 200000, replace=False)
                xyz_preview = xyz[indices]
            else:
                xyz_preview = xyz

            pcd_preview = o3d.geometry.PointCloud()
            pcd_preview.points = o3d.utility.Vector3dVector(xyz_preview)
            self.original_pcd = pcd_preview

            self.signals.update_progress.emit(50)

            # 自动显示点云
            self.signals.append_log.emit("🖥️ 自动显示点云预览...")
            self.signals.update_vtk_scene.emit(pcd_preview, [])
            self.signals.switch_to_vtk.emit()

            self.signals.append_log.emit(f"✅ 点云显示完成 ({len(xyz_preview)} 点)")
            self.signals.update_progress.emit(100)

        except Exception as e:
            self.signals.append_log.emit(f"❌ 点云加载失败: {str(e)}")
            self.signals.update_progress.emit(0)

    def run_downsampling_thread(self, input_path):
        """后台下采样线程"""
        try:
            output_path = os.path.join(os.getcwd(), "output", "point_2.las")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            self.signals.append_log.emit("🔄 开始点云下采样处理...")

            run_voxel_downsampling(
                input_path=input_path,
                output_path=output_path,
                voxel_size=0.1,
                chunk_size=500000,
                progress_callback=self.signals.update_progress.emit,
                log_callback=self.signals.append_log.emit
            )

            # 加载下采样后的点云
            las = laspy.read(output_path)
            xyz = np.vstack((las.x, las.y, las.z)).T
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(xyz)
            self.downsampled_pcd = pcd
            self.original_pcd = pcd  # 更新原始点云为下采样后的版本

            self.signals.append_log.emit(f"✅ 点云下采样完成，文件已保存：{output_path}")
            self.signals.update_vtk_scene.emit(pcd, [])
        except Exception as e:
            self.signals.append_log.emit(f"❌ 下采样失败: {str(e)}")
            print(f"下采样错误详情: {e}")
            import traceback
            traceback.print_exc()

    def vtk_view_display_safe(self, pcd, towers):
        """安全的VTK视图更新 - 加强版本"""
        try:
            # 检查输入数据
            point_count = 0
            if pcd is not None:
                points = np.asarray(pcd.points)
                point_count = len(points)

            tower_count = len(towers) if towers else 0

            self.log_output.append(f"🖥️ 开始更新VTK显示: {point_count} 个点, {tower_count} 个杆塔")

            # 确保当前在VTK视图
            if self.right_stack.currentIndex() != 0:
                self.right_stack.setCurrentIndex(0)
                self.log_output.append("📺 已切换到VTK 3D视图")

            # 显示场景
            if pcd is not None and point_count > 0:
                self.vtk_view.display_full_scene(pcd, towers)
                self.log_output.append(f"✅ VTK场景更新成功 - {point_count} 点 + {tower_count} 杆塔")
            else:
                self.log_output.append("⚠️ 点云数据为空，只显示杆塔")
                if towers:
                    # 创建空点云，只显示杆塔
                    empty_pcd = o3d.geometry.PointCloud()
                    self.vtk_view.display_full_scene(empty_pcd, towers)

        except Exception as e:
            error_msg = f"VTK显示失败: {str(e)}"
            self.log_output.append(f"❌ {error_msg}")
            print(f"VTK显示错误详情: {e}")
            import traceback
            traceback.print_exc()

    def show_vtk_view(self):
        """显示VTK视图"""
        self.push_view_history()
        self.right_stack.setCurrentIndex(0)

        # 如果有数据，重新显示
        if self.original_pcd is not None:
            tower_geometries_for_vtk = []
            if self.tower_geometries:
                tower_geometries_for_vtk = self.convert_tower_obbs_to_vtk_format(self.tower_geometries)

            self.vtk_view_display_safe(self.original_pcd, tower_geometries_for_vtk)
            self.log_output.append("🖥️ 已切换到VTK 3D视图")
        else:
            self.log_output.append("📺 已切换到VTK视图（暂无数据）")

    def import_gim_file_threaded(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "导入GIM文件", "", "GIM Files (*.gim);;All Files (*)")
        if file_path:
            threading.Thread(target=self.import_gim_file, args=(file_path,)).start()

    def import_gim_file(self, file_path):
        """更新导入GIM文件方法，保存原始文件路径"""
        try:
            # 保存原始GIM文件路径
            self.original_gim_file_path = file_path

            output_dir = os.path.join(os.getcwd(), 'output_gim')
            os.makedirs(output_dir, exist_ok=True)
            self.signals.append_log.emit(f"📦📦 开始解压 GIM 文件: {file_path}")
            self.signals.update_progress.emit(10)
            extractor = GIMExtractor(gim_file=file_path, output_folder=output_dir)
            extracted_path = extractor.extract_embedded_7z()
            self.signals.update_progress.emit(50)
            self.signals.append_log.emit(f"✅ 解压完成，输出目录: {extracted_path}")

            parser = GIMTower(extracted_path, log_callback=self.signals.append_log.emit)
            towers = parser.parse()
            self.cbm_filenames = parser.get_cbm_filenames()

            self.gim_path = extracted_path
            self.tower_list = towers
            self.signals.update_table.emit(towers)
            self.signals.switch_to_table.emit()
            self.signals.update_progress.emit(90)
            self.signals.append_log.emit(f"✅ 成功提取杆塔数：{len(towers)}")
            self.signals.update_progress.emit(100)
        except Exception as e:
            error_msg = f"GIM导入失败：{str(e)}"
            print("❌❌", error_msg)
            QMessageBox.critical(self, "GIM导入失败", error_msg)
            self.signals.append_log.emit(f"❌❌ {error_msg}")

    def fill_gim_table(self, towers):
        headers = ["杆塔编号", "呼高", "杆塔高", "经度", "纬度", "高度", "北方向偏角"]
        self.gim_table.setColumnCount(len(headers))
        self.gim_table.setHorizontalHeaderLabels(headers)
        self.gim_table.setRowCount(len(towers))

        for row, t in enumerate(towers):
            props = t.get('properties', {})
            self.gim_table.setItem(row, 0, QTableWidgetItem(str(props.get('杆塔编号', ''))))
            self.gim_table.setItem(row, 1, QTableWidgetItem(str(props.get('呼高', ''))))
            self.gim_table.setItem(row, 2, QTableWidgetItem(str(props.get('杆塔高', ''))))
            self.gim_table.setItem(row, 3, QTableWidgetItem(str(t.get('lng', ''))))
            self.gim_table.setItem(row, 4, QTableWidgetItem(str(t.get('lat', ''))))
            self.gim_table.setItem(row, 5, QTableWidgetItem(str(t.get('h', ''))))
            self.gim_table.setItem(row, 6, QTableWidgetItem(str(t.get('r', ''))))

        self.gim_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for col in range(self.gim_table.columnCount()):
            for row in range(self.gim_table.rowCount()):
                item = self.gim_table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def downsample_and_extract(self):
        """执行下采样后再进行杆塔提取"""
        try:
            self.signals.append_log.emit("📉 开始下采样...")
            output_path = os.path.join(os.getcwd(), "output", "point_2.las")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            run_voxel_downsampling(
                input_path=self.pointcloud_path,
                output_path=output_path,
                voxel_size=0.1,
                chunk_size=500000,
                progress_callback=self.signals.update_progress.emit,
                log_callback=self.signals.append_log.emit
            )

            self.signals.append_log.emit("✅ 下采样完成，开始提取杆塔...")
            self.pointcloud_path = output_path  # 用下采样的点云路径替换

            self.run_tower_extraction()  # 用原有逻辑继续提取杆塔

        except Exception as e:
            self.signals.append_log.emit(f"❌ 下采样或提取失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def remove_ground_objects(self):
        """去除地物并提取杆塔 - 修复版本"""
        if self.pointcloud_path is None:
            QMessageBox.warning(self, "未导入点云", "请先导入点云数据！")
            return

        self.log_output.append("🚀🚀 开始去除地物并提取杆塔...")
        self.progress_bar.setValue(0)

        # 立即切换到VTK视图并清空
        self.push_view_history()
        self.right_stack.setCurrentIndex(0)  # 确保显示VTK视图
        self.vtk_view.clear_scene()  # 清空当前场景

        # 在后台线程中运行杆塔提取
        threading.Thread(target=self.downsample_and_extract, daemon=True).start()

    def run_tower_extraction(self):
        """运行杆塔提取算法并自动显示结果"""
        try:
            self.signals.append_log.emit("📂 正在加载原始点云文件...")
            self.signals.update_progress.emit(5)

            # 加载原始点云
            las = laspy.read(self.pointcloud_path)
            xyz = np.vstack((las.x, las.y, las.z)).T

            # 创建点云对象
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(xyz)
            self.original_pcd = pcd

            self.signals.append_log.emit(f"✅ 点云加载完成，共 {len(xyz)} 个点")
            self.signals.update_progress.emit(15)

            # 先显示原始点云
            self.signals.append_log.emit("🖥️ 显示原始点云...")
            self.signals.update_vtk_scene.emit(pcd, [])
            self.signals.update_progress.emit(20)

            # 调用杆塔提取函数
            self.signals.append_log.emit("🔍 开始分析和提取杆塔...")
            tower_obbs = extract_towers(
                self.pointcloud_path,
                progress_callback=lambda p: self.signals.update_progress.emit(int(20 + p * 0.6)),  # 20-80%
                log_callback=self.signals.append_log.emit
            )

            self.signals.update_progress.emit(85)

            if not tower_obbs:
                self.signals.append_log.emit("⚠️ 未检测到杆塔，请检查参数设置")
                self.signals.update_progress.emit(100)
                return

            # 保存杆塔几何体 - 修正：应该保存原始提取的数据
            self.tower_obbs = tower_obbs  # 这里保存原始的OBB数据
            self.tower_geometries = tower_obbs  # 保持兼容性
            self.signals.append_log.emit(f"✅ 成功提取 {len(tower_obbs)} 个杆塔")
            self.signals.update_progress.emit(90)

            # 转换杆塔几何体为VTK可用格式
            self.signals.append_log.emit("🎨 准备显示杆塔...")
            tower_geometries_for_vtk = self.convert_tower_obbs_to_vtk_format_enhanced(tower_obbs)

            # 自动显示结果 - 点云 + 杆塔
            self.signals.append_log.emit("🖥️ 更新3D显示...")
            self.signals.update_vtk_scene.emit(pcd, tower_geometries_for_vtk)

            # 确保切换到VTK视图
            self.signals.switch_to_vtk.emit()

            self.signals.append_log.emit("✅ 去除地物完成，杆塔已自动显示在3D视图中")
            self.signals.update_progress.emit(100)

        except Exception as e:
            error_msg = f"杆塔提取失败: {str(e)}"
            self.signals.append_log.emit(f"❌❌ {error_msg}")
            self.signals.update_progress.emit(0)
            print(f"详细错误: {e}")
            import traceback
            traceback.print_exc()

    def convert_tower_obbs_to_vtk_format_enhanced(self, tower_obbs):
        """增强版的杆塔OBB转换为VTK格式 - 解决矩形框太小的问题"""
        tower_geometries_for_vtk = []

        self.log_output.append(f"🔄 转换 {len(tower_obbs)} 个杆塔几何体（增强版）...")

        for i, tower_info in enumerate(tower_obbs):
            try:
                # 获取杆塔信息
                center = tower_info.get('center')
                extents = tower_info.get('extent')
                rotation = tower_info.get('rotation')

                if center is None or extents is None or rotation is None:
                    self.log_output.append(f"⚠️ 杆塔 {i} 缺少必要信息，跳过")
                    continue

                # 🔧 修复：进一步增大显示框 - 确保完全包裹杆塔
                # 应用更大的放大因子，特别是高度方向
                scale_vector = np.array([2.5, 2.5, 4.0])  # x放大150%，y放大150%，z放大300%
                enhanced_extents = np.array(extents) * scale_vector

                self.log_output.append(f"📏 杆塔{i}: 原始尺寸{extents}, 增强尺寸{enhanced_extents}")

                # 创建增强的OBB
                obb = o3d.geometry.OrientedBoundingBox(center, rotation, enhanced_extents)

                # 创建线框
                lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb)
                line_points = np.asarray(lineset.points)
                lines = np.asarray(lineset.lines)

                # 构造线段的点对（每两个点构成一条线）
                box_pts = []
                for line in lines:
                    box_pts.append(line_points[line[0]])
                    box_pts.append(line_points[line[1]])

                # 添加红色线框 (RGB格式)
                tower_geometries_for_vtk.append((np.array(box_pts), (1.0, 0.0, 0.0)))

                self.log_output.append(f"✅ 杆塔{i}转换成功，中心：{center}, 增强尺寸：{enhanced_extents}")

            except Exception as e:
                self.log_output.append(f"⚠️ 杆塔 {i} 转换失败: {str(e)}")
                continue

        self.log_output.append(f"✅ 成功转换 {len(tower_geometries_for_vtk)} 个增强杆塔几何体")
        return tower_geometries_for_vtk

    def convert_tower_obbs_to_vtk_format(self, tower_obbs):
        """原版的杆塔OBB转换为VTK格式 - 保持向后兼容"""
        return self.convert_tower_obbs_to_vtk_format_enhanced(tower_obbs)

    def extract_tower(self):
        """🔧 提取杆塔功能 - 使用extract.py进行可视化增强（修复版）"""
        if self.pointcloud_path is None:
            QMessageBox.warning(self, "未导入点云", "请先导入点云数据！")
            return

        if not self.tower_obbs:
            QMessageBox.warning(self, "未检测到杆塔", "请先执行'去除地物'步骤提取杆塔信息")
            return

        try:
            self.log_output.append("🔍 使用extract.py增强显示已提取的杆塔...")

            # 自动切换到VTK视图
            self.push_view_history()
            self.right_stack.setCurrentIndex(0)

            # 🔧 使用extract.py提供更好的可视化（修复了变量名错误）
            self.log_output.append("🎨 调用extract.py进行杆塔可视化增强...")

            # 调用extract.py的函数（修复了变量名）
            full_pcd, enhanced_tower_geometries = extract_and_visualize_towers(
                self.pointcloud_path,    # 正确的变量名
                self.tower_obbs,         # 正确的变量名
                use_kuangxuan_method=True,
                kuangxuan_preset="kuangxuan_original"
            )

            self.log_output.append(f"✅ extract.py处理完成，增强杆塔数：{len(enhanced_tower_geometries)}")

            # 显示增强后的结果
            self.vtk_view_display_safe(self.original_pcd, enhanced_tower_geometries)

            self.log_output.append(f"✅ 杆塔增强显示完成，共 {len(self.tower_obbs)} 个杆塔")

        except Exception as e:
            error_msg = f"杆塔显示失败: {str(e)}"
            QMessageBox.critical(self, "杆塔显示失败", error_msg)
            self.log_output.append(f"❌❌ {error_msg}")

            # 如果extract.py失败，回退到原始方法
            self.log_output.append("🔄 回退到原始显示方法...")
            try:
                tower_geometries_for_vtk = self.convert_tower_obbs_to_vtk_format_enhanced(self.tower_obbs)
                self.vtk_view_display_safe(self.original_pcd, tower_geometries_for_vtk)
                self.log_output.append("✅ 使用原始方法显示杆塔成功")
            except Exception as e2:
                self.log_output.append(f"❌ 原始方法也失败: {str(e2)}")

    def review_mode(self):
        self.push_view_history()

        # 调用 build_review_widget 函数，传递 tower_list 参数
        review_widget = build_review_widget(self.tower_list)

        # 更新主界面的 layout 来显示新内容
        layout = self.review_panel.layout()

        # 清空现有的内容
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # 将新的 review_widget 添加到 layout 中
    def review_mode(self):
        self.push_view_history()

        # 调用 build_review_widget 函数，传递 tower_list 参数
        review_widget = build_review_widget(self.tower_list)

        # 更新主界面的 layout 来显示新内容
        layout = self.review_panel.layout()

        # 清空现有的内容
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # 将新的 review_widget 添加到 layout 中
        layout.addWidget(review_widget)
        self.right_stack.setCurrentIndex(2)  # 设置当前显示的面板为校对面板

    def match_only(self):
        """匹配功能 - 也保存匹配后的数据"""
        if not self.tower_list or not self.tower_geometries:
            QMessageBox.warning(self, "数据缺失", "请先导入GIM数据并执行去除地物操作")
            return

        self.push_view_history()
        widget = match_from_gim_tower_list(self.tower_list, self.tower_geometries)

        # 从匹配界面获取数据（如果需要的话）
        self.corrected_data = self.extract_corrected_data_from_widget(widget)

        self._update_review_panel(widget)

    def correct_only(self):
        """校对功能 - 保存校对后的数据"""
        if not self.tower_list or not self.tower_geometries:
            QMessageBox.warning(self, "数据缺失", "请先导入GIM数据并执行去除地物操作")
            return

        self.push_view_history()
        widget = correct_from_gim_tower_list(self.tower_list, self.tower_geometries)

        # 从校对界面获取校对后的数据
        self.corrected_data = self.extract_corrected_data_from_widget(widget)

        self._update_review_panel(widget)
        QMessageBox.information(self, "校对完成", "杆塔位置已根据点云数据校正完成")
        self.statusBar().showMessage("杆塔位置校正完成", 3000)

    def extract_corrected_data_from_widget(self, widget):
        """从校对界面提取校对后的数据"""
        try:
            # 假设widget有左侧表格，我们从中提取数据
            corrected_data = []

            # 查找左侧表格（GIM数据表格）
            left_layout = widget.layout().itemAt(0)  # 左侧布局
            if left_layout and left_layout.layout():
                for i in range(left_layout.layout().count()):
                    item = left_layout.layout().itemAt(i)
                    if item and hasattr(item.widget(), 'rowCount'):  # 是表格
                        table = item.widget()

                        # 提取表格数据
                        for row in range(table.rowCount()):
                            if table.item(row, 0):  # 确保行有数据
                                row_data = {
                                    '杆塔编号': table.item(row, 0).text() if table.item(row, 0) else '',
                                    '纬度': table.item(row, 1).text() if table.item(row, 1) else '0',
                                    '经度': table.item(row, 2).text() if table.item(row, 2) else '0',
                                    '高度': table.item(row, 3).text() if table.item(row, 3) else '0',
                                    '北方向偏角': table.item(row, 4).text() if table.item(row, 4) else '0'
                                }

                                # 添加CBM路径信息（如果原始数据中有）
                                if row < len(self.tower_list):
                                    original_tower = self.tower_list[row]
                                    row_data['CBM路径'] = original_tower.get('cbm_path', '')

                                corrected_data.append(row_data)
                        break

            return corrected_data

        except Exception as e:
            self.log_output.append(f"⚠️ 提取校对数据失败: {str(e)}")
            return []

    def _update_review_panel(self, widget):
        layout = self.review_panel.layout()
        for i in reversed(range(layout.count())):
            old = layout.itemAt(i).widget()
            if old:
                old.setParent(None)
        layout.addWidget(widget)
        self.right_stack.setCurrentIndex(2)

    def save_and_compress(self):
        """更新的保存和压缩功能"""
        try:
            # 检查必要的数据
            if not self.gim_path:
                QMessageBox.warning(self, "缺少数据", "请先导入GIM文件")
                return

            if not self.corrected_data:
                # 如果没有校对数据，使用原始数据
                self.corrected_data = []
                for tower in self.tower_list:
                    props = tower.get('properties', {})
                    corrected_data_item = {
                        '杆塔编号': props.get('杆塔编号', ''),
                        '纬度': tower.get('lat', 0),
                        '经度': tower.get('lng', 0),
                        '高度': tower.get('h', 0),
                        '北方向偏角': tower.get('r', 0),
                        'CBM路径': tower.get('cbm_path', '')
                    }
                    self.corrected_data.append(corrected_data_item)

            # 选择保存位置
            default_name = "updated_project.gim"
            if self.original_gim_file_path:
                default_name = os.path.basename(self.original_gim_file_path).replace('.gim', '_updated.gim')

            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存更新后的GIM文件",
                default_name,
                "GIM Files (*.gim);;All Files (*)"
            )

            if not output_path:
                return

            # 确保文件扩展名正确
            if not output_path.endswith('.gim'):
                output_path += '.gim'

            self.log_output.append("🔄 开始保存校对数据并生成GIM文件...")
            self.progress_bar.setValue(10)

            # 在后台线程中执行保存操作
            threading.Thread(target=self.save_thread, args=(output_path,)).start()

        except Exception as e:
            error_msg = f"保存准备失败：{str(e)}"
            QMessageBox.critical(self, "保存失败", error_msg)
            self.log_output.append(f"❌❌ {error_msg}")

    def save_thread(self, output_path):
        """在后台线程中执行保存操作"""
        try:
            def progress_callback(value):
                self.signals.update_progress.emit(value)

            def log_callback(message):
                self.signals.append_log.emit(message)

            # 使用更新的保存功能
            success = update_and_compress_from_correction(
                extracted_gim_folder=self.gim_path,
                corrected_data=self.corrected_data,
                output_gim_path=output_path,
                original_gim_path=self.original_gim_file_path,
                log_callback=log_callback
            )

            if success:
                self.signals.append_log.emit(f"🎉 保存成功！文件位置: {output_path}")
                progress_callback(100)

                # 可选：询问是否打开文件所在文件夹
                folder_path = os.path.dirname(output_path)
                self.signals.append_log.emit(f"📁 文件保存在: {folder_path}")
            else:
                self.signals.append_log.emit("❌ 保存失败，请查看日志了解详情")
                progress_callback(0)

        except Exception as e:
            error_msg = f"保存失败：{str(e)}"
            self.signals.append_log.emit(f"❌❌ {error_msg}")
            progress_callback(0)

    def progress_bar_update(self, value):
        """进度条更新"""
        self.progress_bar.setValue(value)

    def log_output_append(self, msg):
        """日志输出"""
        self.log_output.append(msg)
        # 自动滚动到底部
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TowerDetectionTool()
    window.show()
    sys.exit(app.exec_())