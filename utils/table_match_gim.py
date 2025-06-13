import math
import numpy as np
import pandas as pd
from pyproj import Transformer
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from PyQt5.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHBoxLayout  # 导入必要的组件
from PyQt5.QtCore import Qt  # 导入 Qt 用于对齐方式


def haversine(lat1, lon1, lat2, lon2):
    """
    使用Haversine公式计算地球上两点之间的距离（单位：米）

    参数:
        lat1, lon1: 点1的纬度和经度
        lat2, lon2: 点2的纬度和经度

    返回:
        两点之间的距离（米）
    """
    R = 6371.0  # 地球半径（公里）
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c * 1000  # 转换为米


def match_towers(gim_list, pointcloud_towers, transformer, distance_threshold=50, height_threshold=100):
    """
    匹配GIM杆塔和点云杆塔（使用转换后的WGS84坐标）

    参数:
        gim_list: GIM杆塔信息列表
        pointcloud_towers: 点云杆塔信息列表（包含转换后的坐标）
        transformer: 坐标转换器
        distance_threshold: 经纬度距离阈值（米）
        height_threshold: 高度差阈值（米）

    返回:
        匹配成功的行索引列表[(gim_index, pc_index)]
    """
    matched_rows = []

    for i, gim_tower in enumerate(gim_list):
        # 获取GIM杆塔位置信息
        gim_lat = gim_tower.get("lat", 0)
        gim_lon = gim_tower.get("lng", 0)
        gim_height = gim_tower.get("h", 0)

        # 尝试匹配点云杆塔
        for j, pc_tower in enumerate(pointcloud_towers):
            # 获取点云杆塔转换后的位置信息
            pc_lon = pc_tower['converted_center'][0]  # 经度(WGS84)
            pc_lat = pc_tower['converted_center'][1]  # 纬度(WGS84)
            pc_height = pc_tower['converted_center'][2]  # 海拔高度

            # 计算距离并检查是否匹配
            distance = haversine(gim_lat, gim_lon, pc_lat, pc_lon)
            height_diff = abs(gim_height - pc_height)

            if distance <= distance_threshold and height_diff <= height_threshold:
                matched_rows.append((i, j))
                break

    return matched_rows


def create_tower_table(headers, data, row_count=None):

    table = QTableWidget()

    # 设置表格行数和列数
    if row_count is None:
        row_count = len(data)
    table.setRowCount(row_count)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

    # 填充数据
    for row in range(row_count):
        if row < len(data):
            row_data = data[row]
            for col in range(min(len(row_data), table.columnCount())):
                item = QTableWidgetItem(str(row_data[col]))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

    # 自适应列宽
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return table


def match_from_gim_tower_list(tower_list, pointcloud_towers):
    """
    创建匹配界面并显示GIM杆塔和点云杆塔信息
    - 左表(GIM数据): 保持原始坐标
    - 右表(点云数据): 显示转换后的WGS84坐标
    - 匹配计算使用转换后的新坐标
    """
    # 创建坐标转换器 (CGCS2000 -> WGS84)
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)

    # 准备左表数据 (GIM杆塔，原始坐标)
    left_data = []
    for t in tower_list:
        left_data.append([
            t.get("properties", {}).get("杆塔编号", ""),  # 杆塔编号
            f"{t.get('lat', 0):.6f}",  # 纬度（原始坐标）
            f"{t.get('lng', 0):.6f}",  # 经度（原始坐标）
            f"{t.get('h', 0):.2f}",  # 高度
            f"{t.get('r', 0):.1f}"  # 方向角
        ])

    # 准备右表数据 (点云杆塔，转换后坐标)
    right_data = []
    converted_towers = []  # 存储转换后的点云杆塔信息

    for i, tower in enumerate(pointcloud_towers):
        # 执行坐标转换
        lon, lat = transformer.transform(
            tower['center'][0],
            tower['center'][1]
        )
        converted_center = [lon, lat, tower['center'][2]]

        # 存储转换后的信息
        converted_tower = {
            'id': f"PC-{i + 1}",
            'converted_center': converted_center,
            'height': tower.get('height', 0),
            'north_angle': tower.get('north_angle', 0),
            'original_center': tower['center']  # 保留原始坐标
        }
        converted_towers.append(converted_tower)

        # 准备表格显示数据
        right_data.append([
            converted_tower['id'],  # 杆塔编号
            f"{lon:.6f}",  # 经度(WGS84)
            f"{lat:.6f}",  # 纬度(WGS84)
            f"{converted_center[2]:.2f}",  # 海拔高度
            f"{converted_tower['height']:.1f}",  # 杆塔高度
            f"{converted_tower['north_angle']:.1f}"  # 北方向偏角
        ])

    # 创建左侧表格 (GIM杆塔，原始坐标)
    left_headers = ["杆塔编号", "纬度(原始)", "经度(原始)", "高度", "北方向偏角"]
    table_left = create_tower_table(left_headers, left_data)

    # 创建右侧表格 (点云杆塔，WGS84坐标)
    right_headers = ["杆塔编号", "经度(WGS84)", "纬度(WGS84)", "海拔高度", "杆塔高度", "北方向偏角"]
    table_right = create_tower_table(right_headers, right_data)

    # === 新增部分 ===
    # 为左表格添加数据来源标签，放在表格上方
    left_label = QLabel("数据来源: GIM 数据")
    left_label.setAlignment(Qt.AlignCenter)  # 标签居中对齐
    left_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")  # 设置红色字体和加粗样式


    # 为右表格添加数据来源标签，放在表格上方
    right_label = QLabel("数据来源: 点云数据")
    right_label.setAlignment(Qt.AlignCenter)  # 标签居中对齐
    right_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")  # 设置红色字体和加粗样式

    # === 新增部分结束 ===

    # 使用转换后的坐标进行匹配
    matched = match_towers(tower_list, converted_towers, transformer)
    highlight_colors = [QColor(173, 216, 230), QColor(255, 255, 204), QColor(220, 220, 220)]
    color_index = 0

    for left_row, right_row in matched:
        # 高亮匹配行
        for col in range(table_left.columnCount()):
            table_left.item(left_row, col).setBackground(highlight_colors[color_index])
        for col in range(table_right.columnCount()):
            table_right.item(right_row, col).setBackground(highlight_colors[color_index])

        color_index = (color_index + 1) % len(highlight_colors)

    # 创建面板
    panel = QWidget()
    # 创建左侧的垂直布局 (标签 + 表格)
    left_layout = QVBoxLayout()
    left_layout.addWidget(left_label)
    left_layout.addWidget(table_left)

    # 创建右侧的垂直布局 (标签 + 表格)
    right_layout = QVBoxLayout()
    right_layout.addWidget(right_label)
    right_layout.addWidget(table_right)

    # 主水平布局
    main_layout = QHBoxLayout(panel)
    main_layout.addLayout(left_layout)
    main_layout.addLayout(right_layout)

    # 附加转换后的数据到面板对象
    panel.converted_towers = converted_towers
    panel.matched_pairs = matched

    return panel


def correct_from_gim_tower_list(tower_list, pointcloud_towers):
    """
    创建校对界面并校正GIM杆塔信息
    - 左表(GIM数据): 保持原始坐标
    - 右表(点云数据): 显示转换后的WGS84坐标
    - 校对使用转换后的坐标
    """
    # 创建坐标转换器 (CGCS2000 -> WGS84)
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)

    # 准备左表数据 (GIM杆塔，原始坐标)
    left_data = []
    for t in tower_list:
        left_data.append([
            t.get("properties", {}).get("杆塔编号", ""),  # 杆塔编号
            f"{t.get('lat', 0):.6f}",  # 纬度（原始坐标）
            f"{t.get('lng', 0):.6f}",  # 经度（原始坐标）
            f"{t.get('h', 0):.2f}",  # 高度
            f"{t.get('r', 0):.1f}"  # 方向角
        ])

    # 准备右表数据 (点云杆塔，转换后坐标)
    right_data = []
    converted_towers = []  # 存储转换后的点云杆塔信息

    for i, tower in enumerate(pointcloud_towers):
        # 执行坐标转换
        lon, lat = transformer.transform(
            tower['center'][0],
            tower['center'][1]
        )
        converted_center = [lon, lat, tower['center'][2]]

        # 存储转换后的信息
        converted_tower = {
            'id': f"PC-{i + 1}",
            'converted_center': converted_center,
            'height': tower.get('height', 0),
            'north_angle': tower.get('north_angle', 0),
            'original_center': tower['center']  # 保留原始坐标
        }
        converted_towers.append(converted_tower)

        # 准备表格显示数据
        right_data.append([
            converted_tower['id'],  # 杆塔编号
            f"{lon:.6f}",  # 经度(WGS84)
            f"{lat:.6f}",  # 纬度(WGS84)
            f"{converted_center[2]:.2f}",  # 海拔高度
            f"{converted_tower['height']:.1f}",  # 杆塔高度
            f"{converted_tower['north_angle']:.1f}"  # 北方向偏角
        ])

    # 创建左侧表格 (GIM杆塔，原始坐标)
    left_headers = ["杆塔编号", "纬度(原始)", "经度(原始)", "高度", "北方向偏角"]
    table_left = create_tower_table(left_headers, left_data)

    # 创建右侧表格 (点云杆塔，WGS84坐标)
    right_headers = ["杆塔编号", "经度(WGS84)", "纬度(WGS84)", "海拔高度", "杆塔高度", "北方向偏角"]
    table_right = create_tower_table(right_headers, right_data)

    # === 新增部分 ===
    # 为左表格添加数据来源标签
    left_label = QLabel("数据来源: GIM 数据")  # 创建左表格的标签
    left_label.setAlignment(Qt.AlignCenter)
    table_left.setHorizontalHeaderItem(0, QTableWidgetItem("数据来源: GIM 数据"))  # 直接在表头加标签

    # 为右表格添加数据来源标签
    right_label = QLabel("数据来源: 点云数据")  # 创建右表格的标签
    right_label.setAlignment(Qt.AlignCenter)
    table_right.setHorizontalHeaderItem(0, QTableWidgetItem("数据来源: 点云数据"))  # 直接在表头加标签
    # === 新增部分结束 ===

    # 使用转换后的坐标进行匹配
    matched = match_towers(tower_list, converted_towers, transformer)
    highlight_colors = [QColor(200, 255, 200), QColor(255, 230, 230), QColor(220, 220, 255)]
    color_index = 0

    for left_row, right_row in matched:
        # 获取点云杆塔转换后的信息
        pc_tower = converted_towers[right_row]

        # 校正GIM杆塔信息（使用转换后的坐标）
        table_left.item(left_row, 0).setText(pc_tower['id'])  # 杆塔编号
        table_left.item(left_row, 1).setText(f"{pc_tower['converted_center'][1]:.6f}")  # 纬度(WGS84)
        table_left.item(left_row, 2).setText(f"{pc_tower['converted_center'][0]:.6f}")  # 经度(WGS84)
        table_left.item(left_row, 3).setText(f"{pc_tower['converted_center'][2]:.2f}")  # 高度
        table_left.item(left_row, 4).setText(f"{pc_tower['north_angle']:.1f}")  # 方向角

        # 高亮显示
        for col in range(table_left.columnCount()):
            table_left.item(left_row, col).setBackground(highlight_colors[color_index])
        for col in range(table_right.columnCount()):
            table_right.item(right_row, col).setBackground(highlight_colors[color_index])

        color_index = (color_index + 1) % len(highlight_colors)

    panel = QWidget()
    # 创建左侧的垂直布局 (标签 + 表格)
    left_layout = QVBoxLayout()
    left_layout.addWidget(left_label)
    left_layout.addWidget(table_left)

    # 创建右侧的垂直布局 (标签 + 表格)
    right_layout = QVBoxLayout()
    right_layout.addWidget(right_label)
    right_layout.addWidget(table_right)

    # 主水平布局
    main_layout = QHBoxLayout(panel)
    main_layout.addLayout(left_layout)
    main_layout.addLayout(right_layout)
    # 附加转换后的数据到面板对象
    panel.converted_towers = converted_towers
    panel.matched_pairs = matched

    return panel