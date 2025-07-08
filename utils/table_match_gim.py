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

# 🔧 新增：导入高程转换器
from utils.elevation_converter import ElevationConverter


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


def convert_pointcloud_ellipsoid_to_orthometric(pointcloud_towers, transformer, region_n_value=25.0):
    """
    🔧 新增函数：将点云杆塔数据从椭球高转换为正高
    注意：这里假设tower_extraction.py输出的是椭球高坐标系(CGCS2000)的数据

    参数:
        pointcloud_towers: 点云杆塔信息列表（椭球高数据）
        transformer: 坐标转换器 (CGCS2000 -> WGS84)
        region_n_value: 区域N值（默认25米）

    返回:
        转换后的点云杆塔列表，包含正高信息
    """
    print("🔄 开始将点云杆塔高程从椭球高转换为正高...")
    print(f"📍 原始点云杆塔数量: {len(pointcloud_towers)}")

    # 初始化高程转换器
    try:
        elev_converter = ElevationConverter(region_n_value=region_n_value)
        print(f"✅ 高程转换器初始化成功，区域N值: {region_n_value}m")
    except Exception as e:
        print(f"⚠️ 高程转换器初始化失败: {str(e)}")
        print("将使用区域经验N值进行转换")
        elev_converter = ElevationConverter(region_n_value=region_n_value)

    converted_towers = []

    for i, tower in enumerate(pointcloud_towers):
        try:
            # 🔧 关键：获取tower_extraction.py输出的椭球高坐标（CGCS2000）
            original_center = tower['center']  # [x_cgcs2000, y_cgcs2000, z_ellipsoid]

            print(f"🔄 处理杆塔{i + 1}: 原始中心 {original_center}")

            # 步骤1：CGCS2000坐标转换到WGS84经纬度
            lon_wgs84, lat_wgs84 = transformer.transform(
                original_center[0],  # X坐标 (CGCS2000)
                original_center[1]  # Y坐标 (CGCS2000)
            )

            # 步骤2：椭球高转换为正高
            ellipsoid_height = original_center[2]  # Z坐标就是椭球高
            orthometric_height = elev_converter.ellipsoid_to_orthometric(
                lat_wgs84, lon_wgs84, ellipsoid_height
            )

            # 🔧 创建包含正高的转换后坐标
            converted_center = [lon_wgs84, lat_wgs84, orthometric_height]

            # 创建转换后的杆塔信息
            converted_tower = {
                'id': f"PC-{i + 1}",  # 初始编号
                'converted_center': converted_center,  # [lon_wgs84, lat_wgs84, orthometric_height]
                'height': tower.get('height', 0),
                'north_angle': tower.get('north_angle', 0),
                'original_center': original_center,  # 保留原始椭球高坐标(CGCS2000)
                # 🔧 详细的高程信息
                'ellipsoid_height': ellipsoid_height,
                'orthometric_height': orthometric_height,
                'n_value': ellipsoid_height - orthometric_height,  # 计算的N值
                'height_conversion_applied': True  # 标记已进行高程转换
            }

            converted_towers.append(converted_tower)

            print(
                f"📊 杆塔{i + 1}: 椭球高 {ellipsoid_height:.2f}m → 正高 {orthometric_height:.2f}m (N={ellipsoid_height - orthometric_height:.2f}m)")

        except Exception as e:
            print(f"⚠️ 杆塔{i + 1} 高程转换失败: {str(e)}")
            # 转换失败时，创建备用数据（使用椭球高）
            try:
                lon_wgs84, lat_wgs84 = transformer.transform(
                    tower['center'][0],
                    tower['center'][1]
                )
                converted_center = [lon_wgs84, lat_wgs84, tower['center'][2]]

                converted_tower = {
                    'id': f"PC-{i + 1}",
                    'converted_center': converted_center,
                    'height': tower.get('height', 0),
                    'north_angle': tower.get('north_angle', 0),
                    'original_center': tower['center'],
                    'ellipsoid_height': tower['center'][2],
                    'orthometric_height': tower['center'][2],  # 转换失败时使用椭球高
                    'n_value': 0,
                    'height_conversion_applied': False
                }
                converted_towers.append(converted_tower)
                print(f"⚠️ 杆塔{i + 1} 使用椭球高作为备选")
            except Exception as e2:
                print(f"❌ 杆塔{i + 1} 完全处理失败: {str(e2)}")
                continue

    print(f"✅ 点云杆塔高程转换完成，共处理 {len(converted_towers)} 个杆塔")

    # 统计转换情况
    successful_conversions = sum(1 for t in converted_towers if t['height_conversion_applied'])
    if successful_conversions > 0:
        n_values = [t['n_value'] for t in converted_towers if t['height_conversion_applied']]
        avg_n_value = np.mean(n_values)
        print(f"📊 成功转换: {successful_conversions}/{len(converted_towers)} 个杆塔")
        print(f"📊 平均N值: {avg_n_value:.2f}m")

    return converted_towers


def match_towers(gim_list, pointcloud_towers, transformer, distance_threshold=50, height_threshold=100,
                 region_n_value=25.0):
    """
    🔧 修改后的匹配函数：在匹配阶段进行椭球高到正高转换

    参数:
        gim_list: GIM杆塔信息列表
        pointcloud_towers: 点云杆塔信息列表（tower_extraction.py的原始椭球高输出）
        transformer: 坐标转换器
        distance_threshold: 经纬度距离阈值（米）
        height_threshold: 高度差阈值（米）
        region_n_value: 区域N值（米）

    返回:
        匹配成功的行索引列表[(gim_index, pc_index)]，以及转换后的点云杆塔数据
    """
    print("🔍 开始杆塔匹配（在匹配阶段进行高程转换）...")

    # 🔧 关键步骤：将点云杆塔从椭球高转换为正高
    converted_towers = convert_pointcloud_ellipsoid_to_orthometric(pointcloud_towers, transformer, region_n_value)

    print(f"🔍 开始执行匹配算法...")
    matched_rows = []

    for i, gim_tower in enumerate(gim_list):
        # 获取GIM杆塔位置信息（假设GIM中已经是正高）
        gim_lat = gim_tower.get("lat", 0)
        gim_lon = gim_tower.get("lng", 0)
        gim_height = gim_tower.get("h", 0)  # GIM中的高度（正高）

        print(f"🔍 匹配GIM杆塔{i + 1}: 位置({gim_lat:.6f}, {gim_lon:.6f}), 正高{gim_height:.2f}m")

        # 🔧 关键：使用转换后的正高数据进行匹配
        for j, pc_tower in enumerate(converted_towers):
            # 获取点云杆塔转换后的位置信息（WGS84 + 正高）
            pc_lon = pc_tower['converted_center'][0]  # 经度(WGS84)
            pc_lat = pc_tower['converted_center'][1]  # 纬度(WGS84)
            pc_height = pc_tower['converted_center'][2]  # 🔧 现在是正高！

            # 计算距离并检查是否匹配
            distance = haversine(gim_lat, gim_lon, pc_lat, pc_lon)
            height_diff = abs(gim_height - pc_height)  # 🔧 现在是正高与正高的比较

            print(f"  📐 vs 点云杆塔{j + 1}: 距离{distance:.1f}m, 高差{height_diff:.1f}m (正高{pc_height:.2f}m)")

            if distance <= distance_threshold and height_diff <= height_threshold:
                matched_rows.append((i, j))
                print(f"  ✅ 匹配成功！GIM杆塔{i + 1} ↔ 点云杆塔{j + 1}")
                break

    print(f"🎉 匹配完成，共找到 {len(matched_rows)} 对匹配的杆塔")
    return matched_rows, converted_towers


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


# 在 table_match_gim.py 中的修改部分

def match_from_gim_tower_list(tower_list, pointcloud_towers, region_n_value=25.0):
    """
    🔧 修改后的匹配功能：在匹配阶段进行高程转换，并以GIM北方向偏角为准更新点云数据
    """
    print("🚀 启动匹配功能（仅在匹配阶段转换高程）...")

    # 创建坐标转换器 (CGCS2000 -> WGS84)
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)

    # 准备左表数据 (GIM杆塔，保持原始数据)
    left_data = []
    for t in tower_list:
        left_data.append([
            t.get("properties", {}).get("杆塔编号", ""),  # 杆塔编号
            f"{t.get('lat', 0):.6f}",  # 纬度
            f"{t.get('lng', 0):.6f}",  # 经度
            f"{t.get('h', 0):.2f}",  # 高程（正高）
            f"{t.get('r', 0):.1f}"  # 方向角
        ])

    # 🔧 关键修改：在匹配阶段执行高程转换
    matched, converted_towers = match_towers(
        tower_list, pointcloud_towers, transformer,
        region_n_value=region_n_value
    )

    # 准备右表数据 (点云杆塔，使用转换后的正高数据)
    right_data = []
    for converted_tower in converted_towers:
        lat = converted_tower['converted_center'][1]
        lon = converted_tower['converted_center'][0]
        orthometric_height = converted_tower['converted_center'][2]  # 正高

        height_display = f"{orthometric_height:.2f}"

        # 🔧 新增：默认使用点云的北方向偏角，但如果匹配成功会被GIM数据覆盖
        north_angle = converted_tower['north_angle']

        right_data.append([
            converted_tower['id'],  # 杆塔编号
            f"{lat:.6f}",  # 纬度(WGS84)
            f"{lon:.6f}",  # 经度(WGS84)
            height_display,  # 正高
            f"{north_angle:.1f}"  # 北方向偏角
        ])

    # 创建表格
    left_headers = ["杆塔编号", "纬度", "经度", "高程", "北方向偏角"]
    table_left = create_tower_table(left_headers, left_data)

    right_headers = ["杆塔编号", "纬度(WGS84)", "经度(WGS84)", "高程", "北方向偏角"]
    table_right = create_tower_table(right_headers, right_data)

    # 标签
    left_label = QLabel("数据来源: GIM 数据")
    left_label.setAlignment(Qt.AlignCenter)
    left_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

    right_label = QLabel("数据来源: 点云数据 (匹配时正高转换)")
    right_label.setAlignment(Qt.AlignCenter)
    right_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

    # 🔧 进行匹配，并更新杆塔编号和北方向偏角
    highlight_colors = [QColor(173, 216, 230), QColor(255, 255, 204), QColor(220, 220, 220)]
    color_index = 0

    for left_row, right_row in matched:
        # 获取GIM杆塔的信息
        gim_tower_id = tower_list[left_row].get("properties", {}).get("杆塔编号", "")
        gim_north_angle = tower_list[left_row].get("r", 0)  # 🔧 获取GIM的北方向偏角

        # 更新右表的杆塔编号
        if table_right.item(right_row, 0):
            table_right.item(right_row, 0).setText(str(gim_tower_id))

        # 🔧 新增：更新右表的北方向偏角为GIM数据的值
        if table_right.item(right_row, 4):
            table_right.item(right_row, 4).setText(f"{gim_north_angle:.1f}")

        # 同时更新converted_towers中的信息（用于后续保存）
        converted_towers[right_row]['id'] = str(gim_tower_id)
        converted_towers[right_row]['north_angle'] = gim_north_angle  # 🔧 更新北方向偏角

        # 高亮显示配对成功的行
        for col in range(table_left.columnCount()):
            if table_left.item(left_row, col):
                table_left.item(left_row, col).setBackground(highlight_colors[color_index])
        for col in range(table_right.columnCount()):
            if table_right.item(right_row, col):
                table_right.item(right_row, col).setBackground(highlight_colors[color_index])

        color_index = (color_index + 1) % len(highlight_colors)

    # 创建面板
    panel = QWidget()
    left_layout = QVBoxLayout()
    left_layout.addWidget(left_label)
    left_layout.addWidget(table_left)

    right_layout = QVBoxLayout()
    right_layout.addWidget(right_label)
    right_layout.addWidget(table_right)

    main_layout = QHBoxLayout(panel)
    main_layout.addLayout(left_layout)
    main_layout.addLayout(right_layout)

    # 附加转换后的数据到面板对象
    panel.converted_towers = converted_towers
    panel.matched_pairs = matched

    return panel


def correct_from_gim_tower_list(tower_list, pointcloud_towers, region_n_value=25.0):
    """
    🔧 修改后的校对功能：在校对阶段进行高程转换，并以GIM北方向偏角为准更新点云数据
    """
    print("🚀 启动校对功能（仅在校对阶段转换高程）...")

    # 创建坐标转换器 (CGCS2000 -> WGS84)
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)

    # 准备左表数据 (GIM杆塔，保持原始数据)
    left_data = []
    for t in tower_list:
        left_data.append([
            t.get("properties", {}).get("杆塔编号", ""),  # 杆塔编号
            f"{t.get('lat', 0):.6f}",  # 纬度
            f"{t.get('lng', 0):.6f}",  # 经度
            f"{t.get('h', 0):.2f}",  # 高程（正高）
            f"{t.get('r', 0):.1f}"  # 方向角
        ])

    # 🔧 关键修改：在校对阶段执行高程转换
    matched, converted_towers = match_towers(
        tower_list, pointcloud_towers, transformer,
        region_n_value=region_n_value
    )

    # 准备右表数据 (点云杆塔，使用转换后的正高数据)
    right_data = []
    for converted_tower in converted_towers:
        lat = converted_tower['converted_center'][1]
        lon = converted_tower['converted_center'][0]
        orthometric_height = converted_tower['converted_center'][2]  # 正高

        height_display = f"{orthometric_height:.2f}"
        north_angle = converted_tower['north_angle']

        right_data.append([
            converted_tower['id'],
            f"{lat:.6f}",
            f"{lon:.6f}",
            height_display,
            f"{north_angle:.1f}"
        ])

    # 创建表格
    left_headers = ["杆塔编号", "纬度", "经度", "高程", "北方向偏角"]
    table_left = create_tower_table(left_headers, left_data)

    right_headers = ["杆塔编号", "纬度(WGS84)", "经度(WGS84)", "高程", "北方向偏角"]
    table_right = create_tower_table(right_headers, right_data)

    # 标签
    left_label = QLabel("数据来源: GIM 数据 (校对模式)")
    left_label.setAlignment(Qt.AlignCenter)
    left_label.setStyleSheet("color: blue; font-weight: bold; font-size: 14px;")

    right_label = QLabel("数据来源: 点云数据 (校对时正高转换)")
    right_label.setAlignment(Qt.AlignCenter)
    right_label.setStyleSheet("color: blue; font-weight: bold; font-size: 14px;")

    # 🔧 校对功能：只对配对成功的杆塔进行双向更新
    highlight_colors = [QColor(200, 255, 200), QColor(255, 230, 230), QColor(220, 220, 255)]
    color_index = 0

    for left_row, right_row in matched:
        pc_tower = converted_towers[right_row]

        # 步骤1：将左表的杆塔编号更新到右表（只有配对成功的）
        gim_tower_id = tower_list[left_row].get("properties", {}).get("杆塔编号", "")
        gim_north_angle = tower_list[left_row].get("r", 0)  # 🔧 获取GIM的北方向偏角

        if table_right.item(right_row, 0):
            table_right.item(right_row, 0).setText(str(gim_tower_id))

        # 🔧 新增：更新右表的北方向偏角为GIM数据的值
        if table_right.item(right_row, 4):
            table_right.item(right_row, 4).setText(f"{gim_north_angle:.1f}")

        # 同时更新converted_towers中的信息（用于后续保存）
        converted_towers[right_row]['id'] = str(gim_tower_id)
        converted_towers[right_row]['north_angle'] = gim_north_angle  # 🔧 更新北方向偏角

        # 🔧 步骤2：将右表的正高坐标数据更新到左表（校对GIM数据）
        if table_left.item(left_row, 1):  # 纬度
            table_left.item(left_row, 1).setText(f"{pc_tower['converted_center'][1]:.6f}")
        if table_left.item(left_row, 2):  # 经度
            table_left.item(left_row, 2).setText(f"{pc_tower['converted_center'][0]:.6f}")
        if table_left.item(left_row, 3):  # 高程（现在是正高）
            table_left.item(left_row, 3).setText(f"{pc_tower['converted_center'][2]:.2f}")

        # 🔧 修改：左表的北方向偏角保持GIM原值不变（不更新）
        # 原来的代码：table_left.item(left_row, 4).setText(f"{pc_tower['north_angle']:.1f}")
        # 现在：保持GIM的北方向偏角不变
        if table_left.item(left_row, 4):
            table_left.item(left_row, 4).setText(f"{gim_north_angle:.1f}")

        # 高亮显示配对成功并已校对的行
        color = highlight_colors[color_index % len(highlight_colors)]
        for col in range(table_left.columnCount()):
            if table_left.item(left_row, col):
                table_left.item(left_row, col).setBackground(color)
        for col in range(table_right.columnCount()):
            if table_right.item(right_row, col):
                table_right.item(right_row, col).setBackground(color)

        color_index += 1

    panel = QWidget()
    left_layout = QVBoxLayout()
    left_layout.addWidget(left_label)
    left_layout.addWidget(table_left)

    right_layout = QVBoxLayout()
    right_layout.addWidget(right_label)
    right_layout.addWidget(table_right)

    main_layout = QHBoxLayout(panel)
    main_layout.addLayout(left_layout)
    main_layout.addLayout(right_layout)

    # 附加转换后的数据到面板对象
    panel.converted_towers = converted_towers
    panel.matched_pairs = matched

    return panel