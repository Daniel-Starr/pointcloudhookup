import sys
import os
import gc
import threading
import numpy as np
import laspy
import open3d as o3d

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QLabel, QSplitter,
    QFileDialog, QMessageBox, QGroupBox, QToolButton, QStyle, QProgressBar,
    QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from ui.import_PC import run_voxel_downsampling
from ui.extract import extract_and_visualize_towers
from ui.vtk_widget import VTKPointCloudWidget
from ui.compress import GIMExtractor
from ui.parsetower import GIMTower

class ProgressSignal(QObject):
    update_progress = pyqtSignal(int)
    append_log = pyqtSignal(str)
    update_vtk_scene = pyqtSignal(object, object)

class TowerDetectionTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("点云校准工具")
        self.setGeometry(300, 100, 1400, 800)
        self.signals = ProgressSignal()
        self.signals.update_progress.connect(self.progress_bar_update)
        self.signals.append_log.connect(self.log_output_append)
        self.signals.update_vtk_scene.connect(self.vtk_view_display_safe)
        self.init_ui()
        self.pointcloud_path = None
        self.downsampled_pcd = None
        self.tower_list = []
        self.gim_path = None

    def init_ui(self):
        button_layout = QHBoxLayout()
        self.buttons = {}
        for name in ["导入GIM", "导入点云", "去除地物", "提取杆塔", "校对"]:
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

        right_widget = QWidget()
        right_layout = QVBoxLayout()

        self.vtk_view = VTKPointCloudWidget()
        right_layout.addWidget(self.vtk_view)

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
        self.buttons["提取杆塔"].clicked.connect(self.extract_tower)
        self.buttons["导入GIM"].clicked.connect(self.import_gim_file_threaded)

    def import_pointcloud(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入点云", "", "LAS Files (*.las *.laz);;All Files (*)"
        )
        if file_path:
            self.pointcloud_path = file_path
            self.progress_bar.setValue(0)
            self.log_output.append("✅ 点云数据导入成功")
            threading.Thread(target=self.run_downsampling_thread, args=(file_path,), daemon=True).start()

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
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入GIM文件", "", "GIM Files (*.gim);;All Files (*)"
        )
        if file_path:
            threading.Thread(target=self.import_gim_file, args=(file_path,), daemon=True).start()

    def import_gim_file(self, file_path):
        try:
            output_dir = os.path.join(os.getcwd(), 'output_gim')
            os.makedirs(output_dir, exist_ok=True)

            self.signals.append_log.emit(f"📦 开始解压 GIM 文件: {file_path}")
            self.signals.update_progress.emit(10)

            extractor = GIMExtractor(gim_file=file_path, output_folder=output_dir)
            extracted_path = extractor.extract_embedded_7z()

            self.signals.update_progress.emit(50)
            self.signals.append_log.emit(f"✅ 解压完成，输出目录: {extracted_path}")

            parser = GIMTower(gim_file=extracted_path)
            towers = parser.parse()

            self.gim_path = extracted_path
            self.tower_list = towers

            self.signals.update_progress.emit(90)
            self.signals.append_log.emit(f"✅ 成功提取杆塔数：{len(towers)}")
            for t in towers:
                name = t.get('properties', {}).get('杆塔编号', t.get('name', '未知'))
                self.signals.append_log.emit(f"   - 杆塔：{name}")

            self.signals.update_progress.emit(100)

        except Exception as e:
            error_msg = f"GIM导入失败：{str(e)}"
            print("❌", error_msg)
            QMessageBox.critical(self, "GIM导入失败", error_msg)
            self.signals.append_log.emit(f"❌ {error_msg}")

    def extract_tower(self):
        if self.downsampled_pcd is None:
            QMessageBox.warning(self, "未导入点云", "请先导入并处理点云！")
            return

        parsed_text = '''✅ 杆塔8: 17.4m高 | 20.1m宽 | 中心坐标[4.37587898e+05 3.14069158e+06 1.31457350e+02]
✅ 杆塔188: 29.8m高 | 10.2m宽 | 中心坐标[4.37787178e+05 3.14000696e+06 8.77722064e+01]
✅ 杆塔199: 21.8m高 | 16.6m宽 | 中心坐标[4.37908948e+05 3.13960682e+06 8.00563301e+01]
✅ 杆塔235: 21.0m高 | 13.0m宽 | 中心坐标[4.37676583e+05 3.14037950e+06 8.25588932e+01]'''

        try:
            full_pcd, tower_geometries = extract_and_visualize_towers(self.pointcloud_path, parsed_text)
            self.downsampled_pcd = full_pcd
            self.signals.update_vtk_scene.emit(full_pcd, tower_geometries)
            self.log_output.append("✅ 杆塔提取与可视化完成")
        except Exception as e:
            QMessageBox.critical(self, "杆塔提取失败", str(e))

    def progress_bar_update(self, value):
        self.progress_bar.setValue(value)

    def log_output_append(self, msg):
        self.log_output.append(msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TowerDetectionTool()
    window.show()
    sys.exit(app.exec_())
