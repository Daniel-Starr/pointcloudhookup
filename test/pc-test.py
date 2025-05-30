import sys

import pandas as pd
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPushButton, QFileDialog
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

import numpy as np

def calculate_distance(lon1, lat1, lon2, lat2):
    """计算经纬度之间的距离（单位：米）"""
    R = 6371.0  # 地球半径（公里）
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distance = R * c
    return distance * 1000  # 转换为米

class ExcelPairingApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("配对 Excel 数据")
        self.setGeometry(300, 100, 800, 600)

        self.tableWidget = QTableWidget(self)
        self.loadButton = QPushButton("加载 Excel 文件", self)
        self.matchButton = QPushButton("执行配对", self)

        self.loadButton.clicked.connect(self.load_excel_data)
        self.matchButton.clicked.connect(self.match_coordinates_and_highlight)

        layout = QVBoxLayout()
        layout.addWidget(self.loadButton)
        layout.addWidget(self.matchButton)
        layout.addWidget(self.tableWidget)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.data_ref = None  # 存储参考文件数据（p35_p38_shuffled.xlsx）
        self.data_match = None  # 存储被匹配文件数据（tower.xlsx）

    def load_excel_data(self):
        # 打开文件对话框，选择参考文件（p35_p38_shuffled.xlsx）
        file_path, _ = QFileDialog.getOpenFileName(self, "选择参考 Excel 文件", "", "Excel Files (*.xlsx);;All Files (*)")
        if file_path:
            try:
                # 使用 pandas 读取 Excel 文件
                self.data_ref = pd.read_excel(file_path)

                # 打开文件对话框，选择被匹配文件（tower.xlsx）
                match_file_path, _ = QFileDialog.getOpenFileName(self, "选择被匹配 Excel 文件", "", "Excel Files (*.xlsx);;All Files (*)")
                if match_file_path:
                    self.data_match = pd.read_excel(match_file_path)

                    # 设置 QTableWidget 的行数和列数
                    self.tableWidget.setRowCount(self.data_ref.shape[0] + self.data_match.shape[0])  # 设置行数
                    self.tableWidget.setColumnCount(self.data_ref.shape[1])  # 设置列数

                    # 设置表格的列名
                    self.tableWidget.setHorizontalHeaderLabels(self.data_ref.columns)

                    # 加载参考数据和被匹配数据到 QTableWidget
                    for row in range(self.data_ref.shape[0]):
                        for col in range(self.data_ref.shape[1]):
                            self.tableWidget.setItem(row, col, QTableWidgetItem(str(self.data_ref.iloc[row, col])))

                    for row in range(self.data_match.shape[0]):
                        for col in range(self.data_match.shape[1]):
                            self.tableWidget.setItem(self.data_ref.shape[0] + row, col, QTableWidgetItem(str(self.data_match.iloc[row, col])))

                    # 刷新表格显示
                    self.tableWidget.resizeColumnsToContents()
                    self.tableWidget.resizeRowsToContents()
                    self.tableWidget.setEditTriggers(QTableWidget.DoubleClicked)  # 允许单元格编辑
                    self.tableWidget.setSelectionBehavior(QTableWidget.SelectRows)  # 选择整行

            except Exception as e:
                print(f"加载文件时出错: {e}")

    def match_coordinates_and_highlight(self):
        """执行数据配对并高亮显示匹配项"""
        if self.data_ref is None or self.data_match is None:
            print("数据尚未加载，请先加载 Excel 文件。")
            return

        matched_indices = []

        # 获取参考文件和被匹配文件中的经纬度列
        ref_lon = self.data_ref['经度']
        ref_lat = self.data_ref['纬度']
        match_lon = self.data_match['经度']
        match_lat = self.data_match['纬度']

        # 遍历参考文件数据，并与被匹配文件数据进行配对
        for ref_row in range(len(self.data_ref)):
            ref_lon_val = ref_lon.iloc[ref_row]
            ref_lat_val = ref_lat.iloc[ref_row]

            for match_row in range(len(self.data_match)):
                match_lon_val = match_lon.iloc[match_row]
                match_lat_val = match_lat.iloc[match_row]

                # 计算经纬度之间的距离
                distance = calculate_distance(ref_lon_val, ref_lat_val, match_lon_val, match_lat_val)

                if distance <= 50:  # 如果距离小于50米，则认为配对成功
                    matched_indices.append((ref_row, match_row))
                    break

        # 更新表格并高亮显示匹配项
        self.update_table_with_matches(matched_indices)

    def update_table_with_matches(self, matched_indices):
        """高亮显示匹配项"""
        for ref_row, match_row in matched_indices:
            # 高亮左边的匹配项（参考数据）
            for col in range(self.tableWidget.columnCount()):
                ref_item = self.tableWidget.item(ref_row, col)
                if ref_item:
                    ref_item.setBackground(QColor(255, 255, 0))  # 黄色高亮

            # 高亮右边的匹配项（被匹配数据）
            for col in range(self.tableWidget.columnCount()):
                match_item = self.tableWidget.item(len(self.data_ref) + match_row, col)
                if match_item:
                    match_item.setBackground(QColor(255, 255, 0))  # 黄色高亮

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExcelPairingApp()
    window.show()
    sys.exit(app.exec_())
