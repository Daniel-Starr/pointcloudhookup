import pandas as pd
import math
from PyQt5.QtWidgets import QWidget, QTableWidget, QHBoxLayout, QTableWidgetItem, QHeaderView, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2 - lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2 - lon1)/2)**2
    return 2 * R * math.asin(math.sqrt(a)) * 1000

def match_and_highlight(gim_list, df_right, distance_threshold=50, height_threshold=100):
    matched_rows = []
    for i, t in enumerate(gim_list):
        lat1, lon1, h1 = t.get("lat", 0), t.get("lng", 0), t.get("h", 0)
        for j in range(len(df_right)):
            lat2 = df_right.at[j, "纬度"]
            lon2 = df_right.at[j, "经度"]
            h2 = df_right.at[j, "高度"]
            if haversine(lat1, lon1, lat2, lon2) <= distance_threshold and abs(h1 - h2) <= height_threshold:
                matched_rows.append((i, j))
                break
    return matched_rows

def match_from_gim_tower_list(tower_list):
    headers = ["杆塔编号", "纬度", "经度", "高度", "北方向偏角"]
    table_left = QTableWidget()
    table_left.setRowCount(len(tower_list))
    table_left.setColumnCount(len(headers))
    table_left.setHorizontalHeaderLabels(headers)

    for row, t in enumerate(tower_list):
        values = [
            str(t.get("properties", {}).get("杆塔编号", "")),
            str(t.get("lat", "")),
            str(t.get("lng", "")),
            str(t.get("h", "")),
            str(t.get("r", ""))
        ]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignCenter)
            table_left.setItem(row, col, item)
    table_left.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    df_right = pd.read_excel(r"E:\\pointcloudhookup\\p35_p38_shuffled.xlsx")
    table_right = QTableWidget()
    table_right.setRowCount(len(df_right))
    table_right.setColumnCount(len(df_right.columns))
    table_right.setHorizontalHeaderLabels(df_right.columns)

    for row in range(len(df_right)):
        for col in range(len(df_right.columns)):
            item = QTableWidgetItem(str(df_right.iat[row, col]))
            item.setTextAlignment(Qt.AlignCenter)
            table_right.setItem(row, col, item)
    table_right.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    matched = match_and_highlight(tower_list, df_right)
    highlight_colors = [QColor(173, 216, 230), QColor(255, 255, 204)]
    color_index = 0

    for left_row, right_row in matched:
        for col in range(table_left.columnCount()):
            table_left.item(left_row, col).setBackground(highlight_colors[color_index])
        for col in range(table_right.columnCount()):
            table_right.item(right_row, col).setBackground(highlight_colors[color_index])
        color_index = (color_index + 1) % len(highlight_colors)

    panel = QWidget()
    layout = QHBoxLayout(panel)
    layout.addWidget(table_left)
    layout.addWidget(table_right)
    return panel

def correct_from_gim_tower_list(tower_list):
    headers = ["纬度", "经度", "高度", "北方向偏角"]
    table_left = QTableWidget()
    table_left.setRowCount(len(tower_list))
    table_left.setColumnCount(len(headers))
    table_left.setHorizontalHeaderLabels(headers)

    for row, t in enumerate(tower_list):
        values = [
            str(t.get("lat", "")),
            str(t.get("lng", "")),
            str(t.get("h", "")),
            str(t.get("r", ""))
        ]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignCenter)
            table_left.setItem(row, col, item)
    table_left.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    df_right = pd.read_excel(r"E:\pointcloudhookup\p35_p38_shuffled.xlsx")
    table_right = QTableWidget()
    table_right.setRowCount(len(df_right))
    table_right.setColumnCount(len(df_right.columns))
    table_right.setHorizontalHeaderLabels(df_right.columns)

    for row in range(len(df_right)):
        for col in range(len(df_right.columns)):
            item = QTableWidgetItem(str(df_right.iat[row, col]))
            item.setTextAlignment(Qt.AlignCenter)
            table_right.setItem(row, col, item)
    table_right.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    matched = match_and_highlight(tower_list, df_right)
    highlight_colors = [QColor(200, 255, 200), QColor(255, 230, 230)]
    color_index = 0

    for left_row, right_row in matched:
        # ✅ 修改左表格数据
        table_left.item(left_row, 0).setText(str(df_right.at[right_row, "纬度"]))
        table_left.item(left_row, 1).setText(str(df_right.at[right_row, "经度"]))
        table_left.item(left_row, 2).setText(str(df_right.at[right_row, "高度"]))

        # 高亮显示
        for col in range(table_left.columnCount()):
            table_left.item(left_row, col).setBackground(highlight_colors[color_index])
        for col in range(table_right.columnCount()):
            table_right.item(right_row, col).setBackground(highlight_colors[color_index])

        color_index = (color_index + 1) % len(highlight_colors)

    panel = QWidget()
    layout = QHBoxLayout(panel)
    layout.addWidget(table_left)
    layout.addWidget(table_right)
    return panel