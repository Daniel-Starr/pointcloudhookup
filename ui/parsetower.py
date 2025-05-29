import os
import pandas as pd

class GIMTower:
    def __init__(self, gim_file, log_callback=None):
        self.gim_file = gim_file
        self.cbm_path = os.path.join(gim_file, 'Cbm')
        self.arr = []
        self.log = log_callback or print
        self.cbm_files = []
        self.visited_cbm_set = set()  # ✅ 用于去重

    def log_info(self, msg, level="info"):
        if self.log and level != "debug":
            self.log(msg)

    def parse(self):
        project_path = self.parse_project()
        self.build_tree(project_path)
        self.log_info("✅ GIM 文件解析完成，共解析杆塔数：" + str(len(self.arr)))
        self.arr = self.deduplicate_by_cbm_path(self.arr)  # ✅ 去重
        self.export_to_excel()
        return self.arr

    def parse_project(self):
        return os.path.join(self.cbm_path, 'project.cbm')

    def build_tree(self, project_path):
        try:
            with open(project_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("SUBSYSTEM="):
                        cbm_file = line.split('=')[1].strip()
                        if cbm_file not in self.cbm_files:
                            self.cbm_files.append(cbm_file)
                        full_cbm_path = os.path.join(self.cbm_path, cbm_file)
                        self.parse_cbm(full_cbm_path)
        except Exception as e:
            self.log_info(f"❌ project.cbm 解析失败: {e}", level="error")

    def parse_cbm(self, cbm_path, isF4=False):
        cbm_filename = os.path.basename(cbm_path)
        if cbm_filename in self.visited_cbm_set:
            return None  # ✅ 已解析，跳过
        self.visited_cbm_set.add(cbm_filename)

        if cbm_filename not in self.cbm_files:
            self.cbm_files.append(cbm_filename)

        node = {
            'name': '',
            'type': '',
            'lng': '',
            'lat': '',
            'h': '',
            'r': '',
            'properties': '',
            'cbm_path': cbm_filename
        }
        try:
            with open(cbm_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("ENTITYNAME="):
                        node['name'] = line.split('=')[1].strip()
                    elif line.startswith("GROUPTYPE="):
                        group_type = line.split('=')[1].strip()
                        if group_type == 'TOWER':
                            node['type'] = 'TOWER'
                            self.arr.append(node)
                    elif line.startswith("BLHA="):
                        blha = line.split('=')[1].replace(',', ' ', -1).strip()
                        [node['lat'], node['lng'], node['h'], node['r']] = [float(x) for x in blha.split(' ')[:4]]
                    elif line.startswith("BASEFAMILY="):
                        fam_path = line.split('=')[1].strip()
                        if fam_path == '':
                            continue
                        full_fam_path = os.path.join(self.cbm_path, fam_path)
                        fam = self.parse_fam(full_fam_path)
                        if isF4:
                            return fam
                        node['properties'] = fam
                    if line.startswith("TOWER="):
                        sub_cbm = line.split('=')[1].strip()
                        if sub_cbm not in self.cbm_files:
                            self.cbm_files.append(sub_cbm)
                        full_cbm_path = os.path.join(self.cbm_path, sub_cbm)
                        node['properties'] = self.parse_cbm(full_cbm_path, True)

                    for key in ["SECTIONS.NUM=", "STRAINSECTIONS.NUM=", "GROUPS.NUM="]:
                        if line.startswith(key):
                            num = int(line.split('=')[1].strip())
                            for i in range(num):
                                sub_cbm = next(f).split('=')[1].strip()
                                if sub_cbm not in self.cbm_files:
                                    self.cbm_files.append(sub_cbm)
                                full_sub_cbm_path = os.path.join(self.cbm_path, sub_cbm)
                                self.parse_cbm(full_sub_cbm_path)
        except FileNotFoundError:
            pass
        except Exception as e:
            self.log_info(f"⚠️ cbm 解析异常: {e}", level="error")
        return None

    def parse_fam(self, fam_path):
        node = {}
        try:
            with open(fam_path, 'r', encoding='utf-8') as f:
                for line in f:
                    [_, k, v] = line.split('=')
                    node[k.strip()] = v.strip()
            return node
        except Exception:
            return None

    def export_to_excel(self, filename="tower_data.xlsx"):
        try:
            data = []
            for t in self.arr:
                props = t.get("properties", {})
                data.append({
                    "系统层级": t.get("name", ""),
                    "系统类型": t.get("type", ""),
                    "经度": t.get("lng", ""),
                    "纬度": t.get("lat", ""),
                    "高度": t.get("h", ""),
                    "北方向偏角": t.get("r", ""),
                    "杆塔编号": props.get("杆塔编号", ""),
                    "呼高": props.get("呼高", ""),
                    "杆塔高": props.get("杆塔高", ""),
                    "CBM路径": t.get("cbm_path", "")
                })
            df = pd.DataFrame(data)
            if os.path.exists(filename):
                os.remove(filename)
            df.to_excel(filename, index=False)
            self.log_info(f"📄 Excel 文件已生成: {filename}")
        except Exception as e:
            self.log_info(f"❌ Excel 导出失败: {e}")

    def deduplicate_by_cbm_path(self, arr):
        seen = set()
        unique = []
        for item in arr:
            cbm = item.get("cbm_path")
            if cbm not in seen:
                unique.append(item)
                seen.add(cbm)
        return unique

    def get_cbm_filenames(self):
        return self.cbm_files

    def length(self):
        return len(self.arr)


def load_towers_from_gim_path(gim_path, log_callback=None):
    parser = GIMTower(gim_path, log_callback=log_callback)
    tower_list = parser.parse()
    return tower_list
