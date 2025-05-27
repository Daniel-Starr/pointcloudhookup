# encoding: utf-8

import os
import uuid
import py7zr

class GIMUtils:
    def generate_unique_filename(self):
        return str(uuid.uuid4()) + ".7z"

    def get_filename(self, full_path):
        if not full_path.endswith(".gim"):
            raise ValueError("❌ 输入的文件路径不是以 .gim 结尾的")
        return os.path.basename(full_path)[:-4]

    def ensure_folder_exists(self, folder_path):
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"✅ 已创建文件夹: {folder_path}")
        else:
            print(f"📁 文件夹已存在: {folder_path}")

utils = GIMUtils()

class GIMExtractor:
    def __init__(self, gim_file, output_folder="output"):
        self.gim_file = gim_file
        self.output_folder = output_folder
        self.gim_header = None

    def extract_embedded_7z(self):
        gim_file = self.gim_file
        output_folder = self.output_folder
        filename = utils.get_filename(gim_file)

        print(f"🔄 正在解压文件：{gim_file}")

        with open(gim_file, 'rb') as f:
            self.gim_header = f.read(776)  # 头部字节
            compressed_data = f.read()

        temp_7z_path = os.path.join(output_folder, utils.generate_unique_filename())
        utils.ensure_folder_exists(output_folder)

        with open(temp_7z_path, 'wb') as temp_file:
            temp_file.write(compressed_data)

        final_output_folder = os.path.join(output_folder, filename)

        try:
            with py7zr.SevenZipFile(temp_7z_path, mode='r') as archive:
                archive.extractall(path=final_output_folder)
        except Exception as e:
            print("❌ 解压失败:", str(e))
            raise

        os.remove(temp_7z_path)
        print(f"✅ 解压完成，输出目录：{final_output_folder}")
        return final_output_folder


# ========= 主程序：直接用你的 GIM 路径 =========

if __name__ == "__main__":
    gim_path = r"G:\Project\pointcloudhookup\线路工程gim模型和点云数据\平江电厂.gim"

    if not os.path.exists(gim_path):
        print("❌ 文件不存在，请检查路径：", gim_path)
        exit(1)

    try:
        extractor = GIMExtractor(gim_file=gim_path)
        output = extractor.extract_embedded_7z()
        print("✅ GIM 文件处理成功，已解压到：", output)
    except Exception as e:
        print("❌ GIM 文件解压失败：", e)
