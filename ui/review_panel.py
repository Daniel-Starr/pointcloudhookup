from PyQt5.QtWidgets import QWidget, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
from PyQt5.QtCore import Qt
import pandas as pd
import os

def build_review_widget(tower_list, preferred_height=400):
    headers = ["杆塔编号", "呼高", "杆塔高", "经度", "纬度", "高度", "北方向偏角"]

    table = QTableWidget()
    if tower_list:
        table.setRowCount(len(tower_list))
    else:
        table.setRowCount(300)  # 显示10行空白表格，保留表头结构
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)

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

    excel_table = QTableWidget()
    excel_path = os.path.join(os.getcwd(), "p35_p38_shuffled.xlsx")

    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
            excel_table.setRowCount(300)
            excel_table.setColumnCount(len(df.columns))
            excel_table.setHorizontalHeaderLabels(df.columns.tolist())

            for row in range(min(len(df), 300)):
                for col in range(len(df.columns)):
                    item = QTableWidgetItem(str(df.iat[row, col]))
                    item.setTextAlignment(Qt.AlignCenter)
                    excel_table.setItem(row, col, item)

            for col in range(excel_table.columnCount()):
                excel_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)

        except Exception as e:
            excel_table.setRowCount(1)
            excel_table.setColumnCount(1)
            excel_table.setItem(0, 0, QTableWidgetItem(f"读取 Excel 失败: {e}"))
    else:
        excel_table.setRowCount(1)
        excel_table.setColumnCount(1)
        excel_table.setItem(0, 0, QTableWidgetItem("⚠️ 未找到 tower_modified.xlsx 文件"))

    table.setSizePolicy(table.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
    excel_table.setSizePolicy(excel_table.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)

    panel = QWidget()
    layout = QHBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(table)
    layout.addWidget(excel_table)
    panel.setLayout(layout)

    return panel
