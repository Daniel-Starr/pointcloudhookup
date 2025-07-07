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
from ui.extract import extract_and_visualize_towers
from ui.vtk_widget import VTKPointCloudWidget
from ui.compress import GIMExtractor
from ui.parsetower import GIMTower  # ✅ 添加类导入
from ui.review_panel import build_review_widget
from ui.save_cbm import run_save_and_compress

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
        self.cbm_filenames = []  # ✅ 存储 CBM 文件名

    def init_ui(self):
        button_layout = QHBoxLayout()
        self.buttons = {}
        for name in ["导入GIM", "导入点云", "去除地物", "提取杆塔", "校对", "保存", "返回"]:
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
        self.buttons["提取杆塔"].clicked.connect(self.extract_tower)
        self.buttons["导入GIM"].clicked.connect(self.import_gim_file_threaded)
        self.buttons["校对"].clicked.connect(self.review_mode)
        self.buttons["保存"].clicked.connect(self.on_save_button_clicked)
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
            self.signals.append_log.emit(f"📦 开始解压 GIM 文件: {file_path}")
            self.signals.update_progress.emit(10)
            extractor = GIMExtractor(gim_file=file_path, output_folder=output_dir)
            extracted_path = extractor.extract_embedded_7z()
            self.signals.update_progress.emit(50)
            self.signals.append_log.emit(f"✅ 解压完成，输出目录: {extracted_path}")

            parser = GIMTower(extracted_path, log_callback=self.signals.append_log.emit)
            towers = parser.parse()
            self.cbm_filenames = parser.get_cbm_filenames()  # ✅ 获取 CBM 文件名

            self.gim_path = extracted_path
            self.tower_list = towers
            self.signals.update_table.emit(towers)
            self.signals.switch_to_table.emit()
            self.signals.update_progress.emit(90)
            self.signals.append_log.emit(f"✅ 成功提取杆塔数：{len(towers)}")
            self.signals.update_progress.emit(100)
        except Exception as e:
            error_msg = f"GIM导入失败：{str(e)}"
            print("❌", error_msg)
            QMessageBox.critical(self, "GIM导入失败", error_msg)
            self.signals.append_log.emit(f"❌ {error_msg}")

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

    def extract_tower(self):
        if self.downsampled_pcd is None:
            QMessageBox.warning(self, "未导入点云", "请先导入并处理点云！")
            return

        parsed_text = '\n'.join([
            f"✅ 杆塔{t.get('properties', {}).get('杆塔编号', t.get('name', f'塔杆{i+1}'))}: {t.get('properties', {}).get('杆塔高', '?')}m高 | {t.get('properties', {}).get('呼高', '?')}m宽 | 中心坐标[{t.get('lng', '?')} {t.get('lat', '?')} {t.get('h', '?')}]"
            for i, t in enumerate(self.tower_list)
        ])

        try:
            full_pcd, tower_geometries = extract_and_visualize_towers(self.pointcloud_path, parsed_text)
            self.downsampled_pcd = full_pcd
            self.signals.update_vtk_scene.emit(full_pcd, tower_geometries)
            self.log_output.append("✅ 杆塔提取与可视化完成")
        except Exception as e:
            QMessageBox.critical(self, "杆塔提取失败", str(e))

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

    def on_save_button_clicked(self):
        self.log_output.clear()
        run_save_and_compress(log_fn=self.log_output.append)



    def progress_bar_update(self, value):
        self.progress_bar.setValue(value)

    def log_output_append(self, msg):
        self.log_output.append(msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TowerDetectionTool()
    window.show()
    sys.exit(app.exec_())