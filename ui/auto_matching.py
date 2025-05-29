import pandas as pd
import numpy as np
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QColor


# 计算经纬度之间的距离（单位：米）
def calculate_distance(lon1, lat1, lon2, lat2):
    R = 6371.0  # 地球半径（公里）
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distance = R * c
    return distance * 1000  # 转换为米


# 匹配经纬度
def match_coordinates(left_data, right_data):
    matched_indices = []

    for right_row in range(len(right_data)):
        right_lon, right_lat = right_data.iloc[right_row]['经度'], right_data.iloc[right_row]['纬度']

        for left_row in range(len(left_data)):
            left_lon, left_lat = left_data.iloc[left_row]['经度'], left_data.iloc[left_row]['纬度']

            distance = calculate_distance(left_lon, left_lat, right_lon, right_lat)

            if distance <= 50:  # 如果距离小于50米则认为配对成功
                matched_indices.append((left_row, right_row))
                break

    return matched_indices



# 更新表格内容并高亮显示匹配项
def update_table_with_matches(left_table, right_table, matched_indices):
    for left_row, right_row in matched_indices:
        # 高亮左边的匹配项
        for col in range(left_table.columnCount()):
            left_item = left_table.item(left_row, col)  # 获取左边表格的项
            if left_item:
                left_item.setBackground(QColor(255, 255, 0))  # 使用黄色高亮

        # 更新左边表格的数据（右边数据写入左边）
        for col in range(left_table.columnCount()):
            if col == 3:  # 经度
                left_table.setItem(left_row, col, QTableWidgetItem(str(right_table.item(right_row, 3).text())))
            elif col == 4:  # 纬度
                left_table.setItem(left_row, col, QTableWidgetItem(str(right_table.item(right_row, 4).text())))
            # 你可以继续更新其他列
            if col == 5:  # 例如：高度
                left_table.setItem(left_row, col, QTableWidgetItem(str(right_table.item(right_row, 5).text())))


# 自动校对函数，监听数据加载
def auto_match_and_highlight(left_table, right_table):
    # 获取左边的数据（从GIM解析的数据）
    left_data = read_left_data_from_gim(left_table)  # 从GIM数据读取左边数据
    # 获取右边的数据（从Excel文件读取）
    right_data = read_right_data_from_excel('p35_p38_shuffled.xlsx')  # 从Excel文件读取右边数据

    # 获取匹配结果
    matched_indices = match_coordinates(left_data, right_data)

    # 更新表格并高亮显示匹配项
    update_table_with_matches(left_table, right_table, matched_indices)


# 读取左边的数据（从GIM解析的数据）
def read_left_data_from_gim(left_table):
    left_data = []
    for row in range(left_table.rowCount()):
        lon = left_table.item(row, 3).text()  # 获取经度列
        lat = left_table.item(row, 4).text()  # 获取纬度列
        if lon and lat:
            left_data.append({'经度': float(lon), '纬度': float(lat)})
    return pd.DataFrame(left_data)


# 读取右边的数据（从Excel文件读取）
def read_right_data_from_excel(excel_path):
    right_data = pd.read_excel(excel_path)
    right_data.columns = right_data.columns.str.strip()  # 清理列名
    return right_data[['经度', '纬度']]  # 只选择经纬度列
