import math
import numpy as np
import pandas as pd
from pyproj import Transformer
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from PyQt5.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHBoxLayout
from PyQt5.QtCore import Qt


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # 地球半径（公里）
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c * 1000  # 转换为米


def match_towers(gim_list, pointcloud_towers, distance_threshold=50, height_threshold=100):
    matched_rows = []

    for i, gim_tower in enumerate(gim_list):
        gim_lat = gim_tower.get("lat", 0)
        gim_lon = gim_tower.get("lng", 0)
        gim_height = gim_tower.get("h", 0)

        for j, pc_tower in enumerate(pointcloud_towers):
            pc_lat = pc_tower['latitude']
            pc_lon = pc_tower['longitude']
            pc_height = pc_tower['altitude']

            distance = haversine(gim_lat, gim_lon, pc_lat, pc_lon)
            height_diff = abs(gim_height - pc_height)

            if distance <= distance_threshold and height_diff <= height_threshold:
                matched_rows.append((i, j))
                break

    return matched_rows


def create_tower_table(headers, data, row_count=None):
    table = QTableWidget()

    if row_count is None:
        row_count = len(data)
    table.setRowCount(row_count)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

    for row in range(row_count):
        if row < len(data):
            row_data = data[row]
            for col in range(min(len(row_data), table.columnCount())):
                item = QTableWidgetItem(str(row_data[col]))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return table


def match_from_gim_tower_list(tower_list, pointcloud_towers, ):
    # 使用您提供的右侧点云数据
    pc_data = {
        "杆塔编号": ["PC-1", "PC-2", "PC-3", "PC-4", "PC-5", "PC-6", "PC-7"],
        "经度(WGS84)": [113.364177, 113.363205, 113.363373, 113.363229, 113.363038, 113.365303, 113.366543],
        "纬度(WGS84)": [28.376950, 28.379824, 28.380078, 28.379745, 28.379539, 28.373667, 28.369945],
        "海拔高度": [89.24, 130.78, 94.96, 106.09, 114.15, 98.67, 94.98],
        "杆塔高度": [36.4, 26.8, 19.1, 41.1, 21.7, 52.5, 49.2],
        "北方向偏角": [346.0, 85.8, 287.8, 237.8, 356.5, 72.2, 329.3]
    }

    # 创建点云数据结构
    pc_towers = []
    for i in range(len(pc_data["杆塔编号"])):
        pc_towers.append({
            'latitude': pc_data["纬度(WGS84)"][i],
            'longitude': pc_data["经度(WGS84)"][i],
            'altitude': pc_data["海拔高度"][i],
            'tower_height': pc_data["杆塔高度"][i],
            'north_angle': pc_data["北方向偏角"][i]
        })

    # 准备点云表格数据
    right_data = []
    for i in range(len(pc_data["杆塔编号"])):
        right_data.append([
            pc_data["杆塔编号"][i],
            f"{pc_data['经度(WGS84)'][i]:.6f}",
            f"{pc_data['纬度(WGS84)'][i]:.6f}",
            f"{pc_data['海拔高度'][i]:.2f}",
            f"{pc_data['杆塔高度'][i]:.1f}",
            f"{pc_data['北方向偏角'][i]:.1f}"
        ])

    # 创建左侧表格数据 (GIM数据)
    left_data = [
        [t.get("properties", {}).get("杆塔编号", ""), f"{t.get('lat', 0):.6f}", f"{t.get('lng', 0):.6f}",
         f"{t.get('h', 0):.2f}", f"{t.get('r', 0):.1f}"]
        for t in tower_list
    ]

    # 创建左侧表格 (GIM杆塔)
    left_headers = ["杆塔编号", "纬度", "经度", "高度", "北方向偏角"]
    table_left = create_tower_table(left_headers, left_data)

    # 创建右侧表格 (点云杆塔)
    right_headers = ["杆塔编号", "经度(WGS84)", "纬度(WGS84)", "海拔高度", "杆塔高度", "北方向偏角"]
    table_right = create_tower_table(right_headers, right_data)

    # 为左表格添加数据来源标签
    left_label = QLabel("数据来源: GIM 数据")
    left_label.setAlignment(Qt.AlignCenter)
    left_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

    # 为右表格添加数据来源标签
    right_label = QLabel("数据来源: 点云数据")
    right_label.setAlignment(Qt.AlignCenter)
    right_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

    # 执行匹配
    matched = match_towers(tower_list, pc_towers)
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

    # 存储匹配结果
    panel.matched_pairs = matched
    panel.pc_towers = pc_towers

    return panel


def correct_from_gim_tower_list(tower_list):
    """创建校对界面并校正GIM杆塔信息"""
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
    pc_towers = []  # 使用内部定义的点云数据
    for i in range(len(pc_data["杆塔编号"])):
        pc_towers.append({
            'id': pc_data["杆塔编号"][i],  # 添加id字段
            'latitude': pc_data["纬度(WGS84)"][i],
            'longitude': pc_data["经度(WGS84)"][i],
            'altitude': pc_data["海拔高度"][i],
            'tower_height': pc_data["杆塔高度"][i],
            'north_angle': pc_data["北方向偏角"][i]
        })

    # 准备左表数据 (GIM杆塔)
    left_data = []
    for t in tower_list:
        left_data.append([
            t.get("properties", {}).get("杆塔编号", ""),  # 杆塔编号
            f"{t.get('lat', 0):.6f}",  # 纬度
            f"{t.get('lng', 0):.6f}",  # 经度
            f"{t.get('h', 0):.2f}",  # 高度
            f"{t.get('r', 0):.1f}"  # 方向角
        ])

    # 准备右表数据 (点云杆塔)
    right_data = []
    for i in range(len(pc_data["杆塔编号"])):
        right_data.append([
            pc_data["杆塔编号"][i],
            f"{pc_data['经度(WGS84)'][i]:.6f}",
            f"{pc_data['纬度(WGS84)'][i]:.6f}",
            f"{pc_data['海拔高度'][i]:.2f}",
            f"{pc_data['杆塔高度'][i]:.1f}",
            f"{pc_data['北方向偏角'][i]:.1f}"
        ])

    # 创建左侧表格 (GIM杆塔)
    left_headers = ["杆塔编号", "纬度", "经度", "高度", "北方向偏角"]
    table_left = create_tower_table(left_headers, left_data)

    # 创建右侧表格 (点云杆塔)
    right_headers = ["杆塔编号", "经度(WGS84)", "纬度(WGS84)", "海拔高度", "杆塔高度", "北方向偏角"]
    table_right = create_tower_table(right_headers, right_data)

    # 为左表格添加数据来源标签
    left_label = QLabel("数据来源: GIM 数据")
    left_label.setAlignment(Qt.AlignCenter)
    left_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

    # 为右表格添加数据来源标签
    right_label = QLabel("数据来源: 点云数据")
    right_label.setAlignment(Qt.AlignCenter)
    right_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

    # 执行匹配 - 使用内部定义的点云数据
    matched = match_towers(tower_list, pc_towers)
    highlight_colors = [QColor(200, 255, 200), QColor(255, 230, 230), QColor(220, 220, 255)]
    color_index = 0

    for left_row, right_row in matched:
        # 获取点云杆塔信息
        pc_tower = pc_towers[right_row]  # 使用内部定义的点云数据

        # 校正GIM杆塔信息
        table_left.item(left_row, 0).setText(pc_tower['id'])  # 杆塔编号
        table_left.item(left_row, 1).setText(f"{pc_tower['latitude']:.6f}")  # 纬度
        table_left.item(left_row, 2).setText(f"{pc_tower['longitude']:.6f}")  # 经度
        table_left.item(left_row, 3).setText(f"{pc_tower['altitude']:.2f}")  # 高度
        table_left.item(left_row, 4).setText(f"{pc_tower['north_angle']:.1f}")  # 方向角

        # 高亮显示
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

    # 存储匹配结果
    panel.matched_pairs = matched
    panel.pc_towers = pc_towers

    return panel