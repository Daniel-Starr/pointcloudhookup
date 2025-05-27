import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
import re
from typing import List, Dict


class GIMExtractor:
    def __init__(self, gim_file: str, output_folder: str = 'output'):
        self.gim_file = gim_file
        self.output_folder = output_folder

    def extract_embedded_7z(self) -> str:
        """解压 .gim 文件中的 zip 内容，并返回解压路径"""
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        temp_folder = tempfile.mkdtemp()
        with open(self.gim_file, 'rb') as f:
            content = f.read()

        start = content.find(b'PK')  # ZIP文件头
        if start == -1:
            raise ValueError("未找到 ZIP 内容，GIM 文件无效")

        with open(os.path.join(temp_folder, 'embedded.zip'), 'wb') as f:
            f.write(content[start:])

        with zipfile.ZipFile(os.path.join(temp_folder, 'embedded.zip'), 'r') as zip_ref:
            zip_ref.extractall(self.output_folder)

        return self.output_folder


class GIMTower:
    def __init__(self, gim_file: str):
        self.gim_file = gim_file
        self.towers = []

    def parse(self) -> List[Dict]:
        """从解压后的 GIM 文件目录中提取杆塔信息"""
        gml_path = self._find_gml_file()
        tree = ET.parse(gml_path)
        root = tree.getroot()
        namespaces = self._get_namespaces(gml_path)

        tower_elements = root.findall('.//core:featureMember', namespaces)
        for element in tower_elements:
            tower_data = self._extract_tower(element, namespaces)
            if tower_data:
                self.towers.append(tower_data)
        return self.towers

    def _find_gml_file(self) -> str:
        for root, _, files in os.walk(self.gim_file):
            for f in files:
                if f.endswith('.gml'):
                    return os.path.join(root, f)
        raise FileNotFoundError("未找到 .gml 文件")

    def _get_namespaces(self, path: str) -> Dict:
        events = ET.iterparse(path, events=['start-ns'])
        return {prefix: uri for prefix, uri in events}

    def _extract_tower(self, element, ns) -> Dict:
        try:
            tower = {}
            name_elem = element.find('.//core:name', ns)
            tower['name'] = name_elem.text if name_elem is not None else '未命名'

            coords_elem = element.find('.//gml:pos', ns)
            if coords_elem is not None:
                coords = list(map(float, coords_elem.text.strip().split()))
                tower['center'] = coords

            properties = {}
            for prop in element.findall('.//core:attribute', ns):
                key_elem = prop.find('.//core:name', ns)
                val_elem = prop.find('.//core:value', ns)
                if key_elem is not None and val_elem is not None:
                    properties[key_elem.text] = val_elem.text
            tower['properties'] = properties

            return tower
        except Exception as e:
            print(f"[跳过] 解析失败: {e}")
            return None
