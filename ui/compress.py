# encoding: utf-8

from io import BytesIO
import os
import shutil
import subprocess
import uuid
import py7zr

class GIMUtils:
    def __init__(self):
        pass

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

    def read_file_to_parse(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        data = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                data[key.strip()] = value.strip()
        return data

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
            self.gim_header = f.read(776)
            compressed_data = f.read()

        utils.ensure_folder_exists(output_folder)
        final_output_folder = os.path.join(output_folder, filename)
        os.makedirs(final_output_folder, exist_ok=True)

        # 使用 BytesIO 解压，不写入临时 .7z 文件
        archive_file = BytesIO(compressed_data)
        with py7zr.SevenZipFile(archive_file, mode='r') as archive:
            archive.extractall(path=final_output_folder)

        print(f"✅ 解压完成，输出目录：{final_output_folder}")
        return final_output_folder

    def has_7z_cli(self):
        return shutil.which("7z") is not None

    def compress_with_7z_cli(self, source_folder, output_7z_path):
        subprocess.run(['7z', 'a', '-mx=1', output_7z_path, source_folder], check=True)

    def compress_with_py7zr(self, source_folder):
        buffer = BytesIO()
        with py7zr.SevenZipFile(buffer, 'w', filters=[{"id": py7zr.FILTER_COPY}]) as archive:
            archive.writeall(source_folder, arcname='')
        return buffer.getvalue()

    def build_custom_file(self, folder_to_compress, output_file, header_path=None):
        if header_path:
            with open(header_path, 'rb') as hf:
                header = hf.read(776)
        else:
            header = self.gim_header

        if len(header) < 776:
            raise ValueError("❌ Header 文件不足 776 字节")

        if self.has_7z_cli():
            print("🧰 使用系统 7z CLI 加速压缩")
            temp_7z_path = output_file + ".tmp.7z"
            self.compress_with_7z_cli(folder_to_compress, temp_7z_path)
            with open(temp_7z_path, 'rb') as f:
                compressed_data = f.read()
            os.remove(temp_7z_path)
        else:
            print("🐍 使用 py7zr 纯 Python 模式压缩（较慢）")
            compressed_data = self.compress_with_py7zr(folder_to_compress)

        with open(output_file, 'wb') as outf:
            outf.write(header)
            outf.write(compressed_data)

        print(f"✅ 封装完成: {output_file}")
