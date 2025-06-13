import sys
import os
import threading
import laspy
import open3d as o3d
import pandas as pd
import numpy as np
import trimesh
from sklearn.cluster import DBSCAN
from pathlib import Path
import gc

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar,
    QTextEdit, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject

from GUI.import_PC import run_voxel_downsampling
from ui.extract import extract_and_visualize_towers
from ui.vtk_widget import VTKPointCloudWidget
from ui.compress import GIMExtractor
from ui.parsetower import GIMTower
from ui.review_panel import build_review_widget
from ui.save_cbm import run_save_and_compress

from utils.table_match_gim import match_from_gim_tower_list
from utils.table_match_gim import correct_from_gim_tower_list


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
        self.buttons["去除地物"].clicked.connect(self.remove_ground_objects)  # 连接新函数
        self.buttons["提取杆塔"].clicked.connect(self.extract_tower)
        self.buttons["导入GIM"].clicked.connect(self.import_gim_file_threaded)
        self.buttons["匹配"].clicked.connect(self.match_only)
        self.buttons["校对"].clicked.connect(self.correct_only)
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

    # 新增：去除地物功能（杆塔提取）
    def remove_ground_objects(self):
        if self.pointcloud_path is None:
            QMessageBox.warning(self, "未导入点云", "请先导入点云数据！")
            return

        self.log_output.append("🚀 开始去除地物并提取杆塔...")
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
            self.signals.append_log.emit(f"❌ 杆塔提取失败: {str(e)}")
            self.signals.update_progress.emit(0)

    def extract_tower(self):
        if self.downsampled_pcd is None:
            QMessageBox.warning(self, "未导入点云", "请先导入并处理点云！")
            return

        parsed_text = '\n'.join([
            f"✅ 杆塔{t.get('properties', {}).get('杆塔编号', t.get('name', f'塔杆{i + 1}'))}: {t.get('properties', {}).get('杆塔高', '?')}m高 | {t.get('properties', {}).get('呼高', '?')}m宽 | 中心坐标[{t.get('lng', '?')} {t.get('lat', '?')} {t.get('h', '?')}]"
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

    def match_only(self):
        if not self.tower_list:
            QMessageBox.warning(self, "缺少数据", "请先导入 GIM 并提取杆塔数据")
            return
        self.push_view_history()
        widget = match_from_gim_tower_list(self.tower_list)
        self._update_review_panel(widget)

    def correct_only(self):
        if not self.tower_list:
            QMessageBox.warning(self, "缺少数据", "请先导入 GIM 并提取杆塔数据")
            return
        self.push_view_history()
        widget = correct_from_gim_tower_list(self.tower_list)
        self._update_review_panel(widget)

    def _update_review_panel(self, widget):
        layout = self.review_panel.layout()
        for i in reversed(range(layout.count())):
            old = layout.itemAt(i).widget()
            if old:
                old.setParent(None)
        layout.addWidget(widget)
        self.right_stack.setCurrentIndex(2)

    def progress_bar_update(self, value):
        self.progress_bar.setValue(value)

    def log_output_append(self, msg):
        self.log_output.append(msg)


# ==================== 杆塔提取函数（封装原功能）====================
def extract_towers(
        input_las_path,
        progress_callback=None,
        log_callback=None,
        eps=8.0,
        min_points=80,
        aspect_ratio_threshold=0.8,
        min_height=15.0,
        max_width=50.0,
        min_width=8
):
    """大尺寸杆塔优化检测函数，返回OBB几何体列表"""
    tower_obbs = []  # 存储杆塔OBB信息

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    def progress(value):
        if progress_callback:
            progress_callback(value)

    output_dir = Path("../output_towers")
    output_dir.mkdir(exist_ok=True)

    # ==================== 数据读取和预处理 ====================
    try:
        log("📂 读取点云文件...")
        progress(5)
        with laspy.open(input_las_path) as las_file:
            las = las_file.read()
            raw_points = np.stack([las.x, las.y, las.z], axis=1).astype(np.float32)
            centroid = np.mean(raw_points, axis=0)
            points = raw_points - centroid
            header_info = {
                "scales": las.header.scales,
                "offsets": las.header.offsets,
                "point_format": las.header.point_format,
                "version": las.header.version,
                "centroid": centroid
            }
            del las
    except Exception as e:
        log(f"⚠️ 文件读取失败: {str(e)}")
        return tower_obbs

    # ==================== 高度过滤优化 ====================
    try:
        log("🔍 执行高度过滤...")
        progress(10)
        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)  # 降低基准高度
        filtered_points = points[z_values > (base_height + 3.0)]  # 提高过滤阈值
        log(f"✅ 高度过滤完成，保留点数: {len(filtered_points)}")
    except Exception as e:
        log(f"⚠️ 高度过滤失败: {str(e)}")
        return tower_obbs

    # ==================== 改进的聚类处理 ====================
    chunk_size = 50000  # 增大分块尺寸
    chunks = [filtered_points[i:i + chunk_size] for i in range(0, len(filtered_points), chunk_size)]
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    log("\n=== 开始聚类处理 ===")
    progress(20)
    for i, chunk in enumerate(chunks):
        try:
            log(f"处理分块 {i + 1}/{len(chunks)} ({len(chunk)}点)")
            clustering = DBSCAN(
                eps=eps,
                min_samples=min_points,
                n_jobs=-1,
                algorithm='ball_tree'  # 使用更高效的算法
            ).fit(chunk)
            chunk_labels = clustering.labels_
            chunk_labels[chunk_labels != -1] += current_label
            all_labels[i * chunk_size:(i + 1) * chunk_size] = chunk_labels
            current_label = np.max(chunk_labels) + 1 if np.any(chunk_labels != -1) else current_label
            progress(20 + int(30 * (i + 1) / len(chunks)))
        except Exception as e:
            log(f"⚠️ 分块聚类失败（块{i}）: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    # ==================== 杆塔检测与去重 ====================
    unique_labels = set(all_labels) - {-1}
    tower_centers = []
    duplicate_threshold = 25.0  # 修改为固定5米阈值

    log(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")
    progress(60)

    for label_idx, label in enumerate(unique_labels):
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 尺寸过滤条件
            height = extents[2]
            width = max(extents[0], extents[1])
            aspect_ratio = height / width

            # 调试信息
            log(f"簇{label} - 高度: {height:.1f}m, 宽度: {width:.1f}m, 高宽比: {aspect_ratio:.1f}")

            if not (height > min_height and min_width < width < max_width and aspect_ratio > aspect_ratio_threshold):
                log(f"  过滤原因: {'高度不足' if height <= min_height else ''} "
                    f"{'宽度越界' if width <= min_width or width >= max_width else ''} "
                    f"{'高宽比不足' if aspect_ratio <= aspect_ratio_threshold else ''}")
                continue

            # 计算正确全局坐标
            obb_center = obb.transform[:3, 3] + centroid

            # 计算北方向偏角
            rotation_matrix = obb.transform[:3, :3]
            x_axis = rotation_matrix[:, 0]
            horizontal_direction = np.array([x_axis[0], x_axis[1], 0])
            if np.linalg.norm(horizontal_direction) > 1e-6:
                horizontal_direction /= np.linalg.norm(horizontal_direction)
            else:
                horizontal_direction = np.array([1, 0, 0])

            angle_rad = np.arctan2(horizontal_direction[1], horizontal_direction[0])
            north_angle = np.degrees(angle_rad)
            if north_angle < 0:
                north_angle += 360
            north_angle = (90 - north_angle) % 360

            # 去重检查
            is_duplicate = False
            for existing in tower_centers:
                if np.linalg.norm(obb_center - existing) < duplicate_threshold:
                    is_duplicate = True
                    break
            if is_duplicate:
                log(f"⚠️ 跳过重复杆塔{label} (中心距: {np.linalg.norm(obb_center - existing):.1f}m)")
                continue

            # 保存杆塔信息
            tower_info = {
                "center": obb_center,
                "rotation": obb.transform[:3, :3],
                "extent": extents,
                "height": height,
                "width": width,
                "north_angle": north_angle
            }
            tower_obbs.append(tower_info)

            # 保存杆塔中心位置
            tower_centers.append(obb_center)

            # 保存点云
            original_points = cluster_points + centroid
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(original_points, None, header_info, output_path, log)

            log(f"✅ 杆塔{label}: {height:.1f}m高 | {width:.1f}m宽 | "
                f"中心坐标{obb_center} | 北偏角: {north_angle:.1f}°")

            progress(60 + int(30 * (label_idx + 1) / len(unique_labels)))

        except Exception as e:
            log(f"⚠️ 簇{label} 处理失败: {str(e)}")
            continue
        finally:
            del cluster_points, cluster_pc, obb
            gc.collect()

    # ==================== 保存杆塔信息到Excel ====================
    if tower_obbs:
        try:
            output_excel_path = "../towers_info.xlsx"
            towers_info = []
            for idx, tower in enumerate(tower_obbs):
                towers_info.append({
                    "ID": idx,
                    "经度": tower['center'][0],
                    "纬度": tower['center'][1],
                    "海拔高度": tower['center'][2],
                    "杆塔高度": tower['height'],
                    "北方向偏角": tower['north_angle']
                })

            df = pd.DataFrame(towers_info)
            df.to_excel(output_excel_path, index=False)
            log(f"\n✅ 杆塔信息已保存到: {output_excel_path}")
            log(f"检测到杆塔数量: {len(tower_obbs)}个")
        except Exception as e:
            log(f"⚠️ 保存Excel失败: {str(e)}")
    else:
        log("\n⚠️ 未检测到任何杆塔，不生成Excel文件")

    progress(95)
    log("✅ 杆塔提取完成")
    return tower_obbs


def _save_tower_las(points, colors, header_info, output_path, log_callback=None):
    """优化的LAS保存函数"""
    try:
        header = laspy.LasHeader(
            point_format=header_info["point_format"],
            version=header_info["version"]
        )
        header.scales = header_info["scales"]
        header.offsets = header_info["offsets"]

        las = laspy.LasData(header)
        las.x = points[:, 0].astype(np.float64)
        las.y = points[:, 1].astype(np.float64)
        las.z = points[:, 2].astype(np.float64)
        las.write(output_path)
        if log_callback:
            log_callback(f"保存成功：{output_path}")
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 保存失败 {output_path}: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TowerDetectionTool()
    window.show()
    sys.exit(app.exec_())