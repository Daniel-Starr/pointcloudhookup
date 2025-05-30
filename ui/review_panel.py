import pandas as pd
import os
import math
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

# Haversine公式计算经纬度差异
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # 地球半径 (单位：公里)

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c * 1000  # 转换为米
    return distance


# 比对并高亮配对成功的行
def match_and_highlight(tower_list, df, distance_threshold=50, height_threshold=100):
    matched_rows = []  # 存储配对成功的行
    for row, t in enumerate(tower_list):
        tower_lat, tower_lon, tower_height = t.get("lat", 0), t.get("lng", 0), t.get("h", 0)
        for shuffled_row in range(len(df)):
            shuffled_lat, shuffled_lon, shuffled_height = df.iloc[shuffled_row]["纬度"], df.iloc[shuffled_row]["经度"], df.iloc[shuffled_row]["高度"]

            # 计算经纬度距离
            distance = haversine(tower_lat, tower_lon, shuffled_lat, shuffled_lon)

            # 计算高度差异
            height_diff = abs(tower_height - shuffled_height)

            # 如果经纬度距离小于50米且高度差异小于height_threshold，标记为配对成功
            if distance <= distance_threshold and height_diff <= height_threshold:
                matched_rows.append((row, shuffled_row))
                break  # 假设每个塔杆只能匹配一个位置

    return matched_rows


# 保存更新后的 tower_list 到 Excel 文件
def save_tower_list(tower_list, filename="updated_tower_list.xlsx"):
    data = []
    for t in tower_list:
        props = t.get('properties', {})
        row = [
            props.get("杆塔编号", ""),
            props.get("呼高", ""),
            props.get("杆塔高", ""),
            t.get("lng", ""),
            t.get("lat", ""),
            t.get("h", ""),
            t.get("r", ""),  # 如果你需要其他属性，可以继续扩展
            t.get("cbm_path", "")  # CBM路径添加到保存的 Excel 文件中
        ]
        data.append(row)

    # 将数据转换为 DataFrame
    df = pd.DataFrame(data, columns=["杆塔编号", "呼高", "杆塔高", "经度", "纬度", "高度", "北方向偏角", "CBM路径"])

    # 保存为 Excel 文件
    df.to_excel(filename, index=False)
    print(f"更新后的 tower_list 已保存为 {filename}")


def build_review_widget(tower_list, preferred_height=400):
    headers = ["杆塔编号", "呼高", "杆塔高", "经度", "纬度", "高度", "北方向偏角"]  # 不包含 CBM 路径

    table = QTableWidget()
    if tower_list:
        table.setRowCount(len(tower_list))
    else:
        table.setRowCount(300)  # 显示10行空白表格，保留表头结构
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

    # 填充 tower_list 数据
    if tower_list:
        for row, t in enumerate(tower_list):
            props = t.get('properties', {})
            cells = [
                str(props.get("杆塔编号", "")),
                str(props.get("呼高", "")),
                str(props.get("杆塔高", "")),
                str(t.get("lng", "")),
                str(t.get("lat", "")),
                str(t.get("h", "")),
                str(t.get("r", ""))
            ]
            for col, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)

    for col in range(table.columnCount()):
        table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)

    # 加载 p35_p38_shuffled.xlsx 文件
    excel_table = QTableWidget()
    excel_path = os.path.join(os.getcwd(), "p35_p38_shuffled.xlsx")

    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
            excel_table.setRowCount(300)
            excel_table.setColumnCount(len(df.columns))
            excel_table.setHorizontalHeaderLabels(df.columns.tolist())

            # 填充 excel 数据
            for row in range(min(len(df), 300)):
                for col in range(len(df.columns)):
                    item = QTableWidgetItem(str(df.iat[row, col]))
                    item.setTextAlignment(Qt.AlignCenter)
                    excel_table.setItem(row, col, item)

            for col in range(excel_table.columnCount()):
                excel_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)

            # 匹配并高亮配对成功的行
            matched_rows = match_and_highlight(tower_list, df)

            highlight_colors = [QColor(173, 216, 230), QColor(255, 255, 204), QColor(255, 240, 245)]  # 淡蓝色，淡黄色，淡粉色
            color_index = 0  # 用于轮流选择颜色

            # 使用不同颜色高亮左侧和右侧的配对项
            for tower_row, excel_row in matched_rows:
                # 高亮左侧表格整行
                for col in range(table.columnCount()):
                    table.item(tower_row, col).setBackground(highlight_colors[color_index])  # 设置不同颜色表示配对成功

                # 高亮右侧表格整行
                for col in range(excel_table.columnCount()):
                    excel_table.item(excel_row, col).setBackground(highlight_colors[color_index])  # 同样为右侧表格设置配对成功的颜色

                # 将右侧表格中的经度、纬度、高度写入左侧表格
                table.item(tower_row, 3).setText(str(df.iat[excel_row, df.columns.get_loc("经度")]))  # 经度列
                table.item(tower_row, 4).setText(str(df.iat[excel_row, df.columns.get_loc("纬度")]))  # 纬度列
                table.item(tower_row, 5).setText(str(df.iat[excel_row, df.columns.get_loc("高度")]))  # 高度列

                # 切换到下一个颜色
                color_index = (color_index + 1) % len(highlight_colors)

            # 保存更新后的 tower_list
            save_tower_list(tower_list)  # 调用保存函数

        except Exception as e:
            excel_table.setRowCount(1)
            excel_table.setColumnCount(1)
            excel_table.setItem(0, 0, QTableWidgetItem(f"读取 Excel 失败: {e}"))
    else:
        excel_table.setRowCount(1)
        excel_table.setColumnCount(1)
        excel_table.setItem(0, 0, QTableWidgetItem("⚠️ 未找到 p35_p38_shuffled.xlsx 文件"))

    table.setSizePolicy(table.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
    excel_table.setSizePolicy(excel_table.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)

    # 将两个表格加入到面板
    panel = QWidget()
    layout = QHBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(table)
    layout.addWidget(excel_table)
    panel.setLayout(layout)

    print(f"Table Data: {tower_list}")
    print(f"Excel Data: {df.head()}")

    return panel
