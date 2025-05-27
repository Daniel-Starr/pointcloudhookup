
import os


class GIMTower:
    def __init__(self, gim_file):
        self.gim_file = gim_file
        self.cbm_path = os.path.join(gim_file, 'Cbm')
        self.arr = []

    def parse(self):
        # 解析入口文件
        project_path = self.parse_project()
        # 构建树形结构
        self.build_tree(project_path)
        # 解析所有文件
        print(f"解析完成！")
        return self.arr
    
    def parse_project(self):
        print(f"🔍 正在查找project.cbm: {self.cbm_path}")
        return os.path.join(self.cbm_path, 'project.cbm')

    def build_tree(self, project_path):
        print(f"🔍 正在解析project.cbm: {project_path}")
        with open(project_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("SUBSYSTEM="):
                    cbm_path = line.split('=')[1].strip()
                    full_cbm_path = os.path.join(self.cbm_path, cbm_path)
                    self.parse_cbm(full_cbm_path)
                    print(f"🔍 正在生成电塔数组！")
    
    def parse_cbm(self, cbm_path, isF4=False):
        node = {
                    'name': '',
                    'type': '',
                    'lng': '',
                    'lat': '',
                    'h':'',
                    'r':'',
                    'properties': '',
                }
        try:
            with open(cbm_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("ENTITYNAME="):
                        node['name'] = line.split('=')[1].strip()
                    elif line.startswith("GROUPTYPE="):
                        group_type = line.split('=')[1].strip()
                        if group_type == 'TOWER':  # 只解析杆塔
                            node['type'] = 'TOWER'
                            self.arr.append(node)
                    elif line.startswith("BLHA="):
                        blha = line.split('=')[1].replace(',', ' ', -1).strip()
                        [node['lat'], node['lng'], node['h'], node['r']] = [float(x) for x in blha.split(' ')[:4]]
                    elif line.startswith("BASEFAMILY="):
                        # 解析属性文件
                        fam_path = line.split('=')[1].strip()
                        if fam_path == '':
                            continue
                        full_fam_path = os.path.join(self.cbm_path, fam_path)
                        fam = self.parse_fam(full_fam_path)
                        if isF4:
                            return fam
                        node['properties'] = fam
                    if line.startswith("TOWER="): 
                        cbm_path = line.split('=')[1].strip()
                        full_cbm_path = os.path.join(self.cbm_path, cbm_path)
                        node['properties'] = self.parse_cbm(full_cbm_path, True)
                    
                    if line.startswith("SECTIONS.NUM="):  # 解析一级子系统
                        num = int(line.split('=')[1].strip())
                        for i in range(num):
                            sub_cbm = next(f).split('=')[1].strip()
                            full_sub_cbm_path = os.path.join(self.cbm_path, sub_cbm)
                            self.parse_cbm(full_sub_cbm_path)
                    elif line.startswith("STRAINSECTIONS.NUM="): #解析二级子系统
                        num = int(line.split('=')[1].strip())
                        for i in range(num):
                            sub_cbm = next(f).split('=')[1].strip()
                            full_sub_cbm_path = os.path.join(self.cbm_path, sub_cbm)
                            self.parse_cbm(full_sub_cbm_path)
                    elif line.startswith("GROUPS.NUM="): #解析三级子系统
                        num = int(line.split('=')[1].strip())
                        for i in range(num):
                            sub_cbm = next(f).split('=')[1].strip()
                            full_sub_cbm_path = os.path.join(self.cbm_path, sub_cbm)
                            self.parse_cbm(full_sub_cbm_path)
        except Exception as e: 
            if e:
                print(f"cbm文件打开失败: {e}")
            return None
        if node['type'] == 'TOWER':  # 杆塔
            # self.arr.append(node)
            pass
        return None

    def parse_fam(self, fam_path):
        node = {}
        # 解析属性文件逻辑
        try:
            with open(fam_path, 'r', encoding='utf-8') as f:
                for line in f:
                    [_, k, v] = line.split('=')
                    node[k.strip()] = v.strip()
            return node
        except Exception as e:
            if e:
                print(f"fam文件打开失败: {e}")
        return None
    
    def csv(self, filename='tower.csv'):
        with open(filename, 'w', encoding='utf-8') as f:
            s = f'系统层级,系统类型,经度,纬度,高度,北方向偏角,杆塔编号,呼高,杆塔高\n'
            for tower in self.arr:
                s += f'{tower["name"]},{tower["type"]},{tower["lng"]},{tower["lat"]},{tower["h"]},{tower["r"]},{tower["properties"]["杆塔编号"]},{tower["properties"]["呼高"]},{tower["properties"]["杆塔高"]}\n'
            f.write(s)
    
    def length(self):
        return len(self.arr)
