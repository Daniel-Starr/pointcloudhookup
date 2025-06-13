import sys
import os
import threading
import numpy as np
import laspy
import open3d as o3d
import pandas as pd

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar,
    QTextEdit, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject

from GUI.import_PC import run_voxel_downsampling
from ui.vtk_widget import VTKPointCloudWidget
from ui.compress import GIMExtractor
from ui.parsetower import GIMTower
from ui.review_panel import build_review_widget
from ui.save_cbm import update_and_compress

from ui.ui.table_match_gim import match_from_gim_tower_list
from ui.ui.table_match_gim import correct_from_gim_tower_list
from utils.tower_extraction import extract_towers


class ProgressSignal(QObject):
    update_progress = pyqtSignal(int)
    append_log = pyqtSignal(str)
    update_vtk_scene = pyqtSignal(object, object)
    update_table = pyqtSignal(list)
    switch_to_table = pyqtSignal()


class TowerDetectionTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("点云校准工具")
        self.setGeometry(300, 100, 1400, 800)
        self.signals = ProgressSignal()
        self.signals.update_progress.connect(self.progress_bar_update)
        self.signals.append_log.connect(self.log_output_append)
        self.signals.update_vtk_scene.connect(self.vtk_view_display_safe)
        self.signals.update_table.connect(self.fill_gim_table)
        self.signals.switch_to_table.connect(self.show_table_view)

        self.view_history = []
        self.init_ui()
        self.pointcloud_path = None
        self.downsampled_pcd = None
        self.tower_list = []
        self.gim_path = None
        self.cbm_filenames = []
        self.tower_geometries = []  # 存储杆塔OBB几何体

        self.tower_list = self.tower_list
        self.corrected_towers = []  # 存储校对后的数据

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
        # self.buttons["提取杆塔"].clicked.connect(self.extract_tower)
        self.buttons["导入GIM"].clicked.connect(self.import_gim_file_threaded)
        self.buttons["匹配"].clicked.connect(self.match_only)
        self.buttons["校对"].clicked.connect(self.correct_towers)
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
        file_path, _ = QFileDialog.getOpenFileName(self, "导入点云", "", "LAS Files (*.las *.laz);;All Files (*)")
        if file_path:
            self.pointcloud_path = file_path
            self.progress_bar.setValue(0)
            self.log_output.append("✅ 点云数据导入成功")
            self.push_view_history()
            self.right_stack.setCurrentIndex(0)
            threading.Thread(target=self.run_downsampling_thread, args=(file_path,)).start()

    def run_downsampling_thread(self, input_path):
        output_path = os.path.join(os.getcwd(), "output", "point_2.las")
        run_voxel_downsampling(
            input_path=input_path,
            output_path=output_path,
            voxel_size=0.1,
            chunk_size=500000,
            progress_callback=self.signals.update_progress.emit,
            log_callback=self.signals.append_log.emit
        )
        self.signals.append_log.emit(f"✅ 点云下采样完成，文件已保存：{output_path}")

        las = laspy.read(output_path)
        xyz = np.vstack((las.x, las.y, las.z)).T
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(xyz)
        self.downsampled_pcd = pcd
        self.signals.update_vtk_scene.emit(pcd, [])

    def vtk_view_display_safe(self, pcd, towers):
        self.vtk_view.display_full_scene(pcd, towers)

    def import_gim_file_threaded(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "导入GIM文件", "", "GIM Files (*.gim);;All Files (*)")
        if file_path:
            threading.Thread(target=self.import_gim_file, args=(file_path,)).start()

    def import_gim_file(self, file_path):
        try:
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

    def remove_ground_objects(self):
        if self.pointcloud_path is None:
            QMessageBox.warning(self, "未导入点云", "请先导入点云数据！")
            return

        self.log_output.append("🚀🚀 开始去除地物并提取杆塔...")
        self.progress_bar.setValue(0)

        # 在后台线程中运行杆塔提取
        threading.Thread(target=self.run_tower_extraction).start()

    def run_tower_extraction(self):
        """运行杆塔提取算法并更新UI"""
        try:
            # 调用杆塔提取函数
            tower_obbs = extract_towers(
                self.pointcloud_path,
                progress_callback=self.signals.update_progress.emit,
                log_callback=self.signals.append_log.emit
            )

            # 更新杆塔几何体
            self.tower_geometries = tower_obbs

            # 重新加载点云以显示杆塔框
            las = laspy.read(self.pointcloud_path)
            xyz = np.vstack((las.x, las.y, las.z)).T
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(xyz)
            self.downsampled_pcd = pcd

            # 更新VTK视图
            self.signals.update_vtk_scene.emit(pcd, tower_obbs)
            self.signals.append_log.emit("✅ 去除地物完成，杆塔已提取并显示")
            self.signals.update_progress.emit(100)
        except Exception as e:
            self.signals.append_log.emit(f"❌❌ 杆塔提取失败: {str(e)}")
            self.signals.update_progress.emit(0)

    def extract_only(self):
        if self.downsampled_pcd is None:
            QMessageBox.warning(self, "未导入点云", "请先导入并处理点云！")
            return

        # 检查是否已有提取的杆塔信息
        if not self.tower_geometries:
            self.log_output.append("⚠️ 请先执行'去除地物'步骤提取杆塔信息")
            return

        try:
            # 重新加载原始点云
            las = laspy.read(self.pointcloud_path)
            points = np.vstack((las.x, las.y, las.z)).T
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)

            # 可视化杆塔
            tower_geometries = []
            for tower_info in self.tower_geometries:
                # 获取杆塔中心位置和尺寸
                center = tower_info['center']
                extents = tower_info['extent']
                rotation = tower_info['rotation']

                # 创建OBB
                obb = o3d.geometry.OrientedBoundingBox(center, rotation, extents)

                # 创建线框
                lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb)
                line_points = np.asarray(lineset.points)
                lines = np.asarray(lineset.lines)

                # 构造线段的点对
                box_pts = []
                for line in lines:
                    box_pts.append(line_points[line[0]])
                    box_pts.append(line_points[line[1]])

                # 添加红色线框
                tower_geometries.append((np.array(box_pts), (1.0, 0.0, 0.0)))

            self.signals.update_vtk_scene.emit(pcd, tower_geometries)
            self.log_output.append("✅ 杆塔可视化完成")
        except Exception as e:
            QMessageBox.critical(self, "杆塔可视化失败", str(e))

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

    # def on_save_button_clicked(self):
    #     self.log_output.clear()
    #     save_and_compress(log_fn=self.log_output.append)

    def match_only(self):
        """执行杆塔匹配操作"""
        if not self.tower_list:
            QMessageBox.warning(self, "数据缺失", "请先导入GIM数据")
            return

        # 使用预定义的点云数据
        pc_data = {
            "杆塔编号": ["PC-1", "PC-2", "PC-3", "PC-4", "PC-5", "PC-6", "PC-7"],
            "经度(WGS84)": [113.364177, 113.363205, 113.363373, 113.363229, 113.363038, 113.365303, 113.366543],
            "纬度(WGS84)": [28.376950, 28.379824, 28.380078, 28.379745, 28.379539, 28.373667, 28.369945],
            "海拔高度": [89.24, 130.78, 94.96, 106.09, 114.15, 98.67, 94.98],
            "杆塔高度": [36.4, 26.8, 19.1, 41.1, 21.7, 52.5, 49.2],
            "北方向偏角": [346.0, 85.8, 287.8, 237.8, 356.5, 72.2, 329.3]
        }

        # 创建点云数据结构
        pointcloud_towers = []
        for i in range(len(pc_data["杆塔编号"])):
            pointcloud_towers.append({
                'latitude': pc_data["纬度(WGS84)"][i],
                'longitude': pc_data["经度(WGS84)"][i],
                'altitude': pc_data["海拔高度"][i],
                'tower_height': pc_data["杆塔高度"][i],
                'north_angle': pc_data["北方向偏角"][i]
            })

        # 调用匹配函数生成匹配界面
        widget = match_from_gim_tower_list(self.tower_list, pointcloud_towers)
        self._update_review_panel(widget)  # 将生成的匹配界面更新到当前界面

        # 显示匹配结果统计
        matched_count = len(widget.matched_pairs)
        total_pc = len(pointcloud_towers)
        self.statusBar().showMessage(f"匹配完成: 找到 {matched_count} 组匹配点 | 点云总数: {total_pc}")

    def correct_towers(self):
        """执行杆塔校对操作"""
        if not self.tower_list:
            QMessageBox.warning(self, "数据缺失", "请先导入GIM数据")
            return

        # 调用校对函数生成校对界面 - 只传递 tower_list 参数
        widget = correct_from_gim_tower_list(self.tower_list)
        self._update_review_panel(widget)  # 将生成的校对界面更新到当前界面

        # 显示校对结果统计
        matched_count = len(widget.matched_pairs)
        total_pc = len(widget.pc_towers)
        self.status_bar.showMessage(f"校对完成: 匹配到 {matched_count} 组杆塔 | 点云总数: {total_pc}")

    def _update_review_panel(self, widget):
        layout = self.review_panel.layout()
        for i in reversed(range(layout.count())):
            old = layout.itemAt(i).widget()
            if old:
                old.setParent(None)
        layout.addWidget(widget)
        self.right_stack.setCurrentIndex(2)

    def run_update_and_compress(self, cbm_folder, df):
        """在后台线程中执行更新和压缩"""
        try:
            self.signals.append_log.emit(f"开始更新CBM文件和压缩...")
            self.signals.append_log.emit(f"使用杆塔数量: {len(df)}")

            # 调用更新和压缩功能
            update_and_compress(cbm_folder, df)

            self.signals.append_log.emit("✅ 保存并压缩成功！")
        except Exception as e:
            self.signals.append_log.emit(f"❌ 处理失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def get_corrected_tower_data(self):
        """获取校对后的杆塔数据"""
        # 检查当前校对面板是否可用
        if hasattr(self, 'review_panel') and self.review_panel.layout().count() > 0:
            review_widget = self.review_panel.layout().itemAt(0).widget()

            # 尝试从校对面板获取更新后的数据
            if hasattr(review_widget, 'get_corrected_towers'):
                return review_widget.get_corrected_towers()

        # 如果没有激活的校对面板，尝试使用原始数据
        if hasattr(self, 'tower_list') and self.tower_list:
            self.log_output.append("⚠️ 使用原始GIM杆塔数据（未校对）")
            return self.tower_list

        # 没有可用数据
        QMessageBox.warning(self, "数据缺失", "没有可用的杆塔数据")
        return []

    def save_and_compress(self):
        """点击"保存"按钮时，直接使用校对后的值执行更新和压缩操作"""
        try:
            # 获取校对后的杆塔数据
            corrected_towers = self.get_corrected_tower_data()

            if not corrected_towers:
                QMessageBox.warning(self, "数据缺失", "没有可用的校对数据")
                return

            # 获取GIM解压目录的路径
            if not hasattr(self, 'gim_path') or not self.gim_path:
                QMessageBox.warning(self, "路径错误", "未导入GIM文件，无法找到CBM文件夹")
                return

            # 构建CBM文件夹路径（假设解压后的GIM文件夹中有一个Cbm子文件夹）
            cbm_folder = os.path.join(self.gim_path, "Cbm")

            # 检查CBM文件夹是否存在
            if not os.path.exists(cbm_folder):
                QMessageBox.warning(self, "文件夹不存在", f"找不到CBM文件夹: {cbm_folder}")
                return

            # 创建包含杆塔数据的DataFrame
            tower_data = []
            for t in corrected_towers:
                tower_data.append({
                    '杆塔编号': t.get('properties', {}).get('杆塔编号', ''),
                    '纬度': t.get('lat', 0.0),
                    '经度': t.get('lng', 0.0),
                    '高度': t.get('h', 0.0),
                    '北方向偏角': t.get('r', 0.0)
                })

            tower_data_df = pd.DataFrame(tower_data)

            # 在后台线程中执行更新和压缩
            threading.Thread(
                target=self.run_update_and_compress,
                args=(cbm_folder, tower_data_df)
            ).start()

        except Exception as e:
            error_msg = f"保存失败：{str(e)}"
            QMessageBox.critical(self, "保存失败", error_msg)
            self.log_output.append(f"❌ {error_msg}")

    def get_corrected_towers(self):
        """返回校对后的杆塔数据"""
        # 如果还没有应用过修改，先应用
        if not self.corrected_towers:
            self.apply_corrections()
        return self.corrected_towers




    def go_back_view(self):
        if self.view_history:
            last_index = self.view_history.pop()
            self.right_stack.setCurrentIndex(last_index)

    def progress_bar_update(self, value):
        self.progress_bar.setValue(value)

    def log_output_append(self, msg):
        self.log_output.append(msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TowerDetectionTool()
    window.show()
    sys.exit(app.exec_())