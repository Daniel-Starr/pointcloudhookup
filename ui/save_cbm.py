# save_cbm.py
import pandas as pd
import shutil
import os
import subprocess
import py7zr
from io import BytesIO


class CBMUpdater:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback or print

    def log(self, message):
        """统一的日志输出"""
        self.log_callback(message)

    def update_cbm_file(self, cbm_file_path, lat, lon, height, rotation):
        """
        更新CBM文件中的BLHA行

        参数:
            cbm_file_path: CBM文件路径
            lat: 纬度（十进制度）
            lon: 经度（十进制度）
            height: 高度（米）
            rotation: 北方向偏角（逆时针，十进制度）
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(cbm_file_path):
                # self.log(f"⚠️ CBM文件不存在: {cbm_file_path}")
                return False

            # 读取现有的CBM文件
            with open(cbm_file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            # 更新BLHA行
            new_blha_line = f"BLHA={lat:.6f},{lon:.6f},{height:.3f},{rotation:.3f}\n"
            updated_lines = []
            blha_found = False

            for line in lines:
                if line.startswith('BLHA='):
                    updated_lines.append(new_blha_line)
                    blha_found = True
                    # self.log(f"📝 更新BLHA行: {new_blha_line.strip()}")
                else:
                    updated_lines.append(line)

            # 如果没有找到BLHA行，添加一行
            if not blha_found:
                updated_lines.append(new_blha_line)
                # self.log(f"➕ 添加BLHA行: {new_blha_line.strip()}")

            # 写入更新后的内容到CBM文件
            with open(cbm_file_path, 'w', encoding='utf-8') as file:
                file.writelines(updated_lines)

            self.log(f"✅ CBM文件更新成功: {cbm_file_path}")
            return True

        except Exception as e:
            self.log(f"❌ CBM文件更新失败 {cbm_file_path}: {str(e)}")
            return False

    def has_7z_cli(self):
        """检查系统是否有7z命令行工具"""
        return shutil.which("7z") is not None

    def compress_with_7z_cli(self, source_folder, output_path):
        """使用7z命令行工具压缩"""
        try:
            # 使用7z压缩，设置为最大压缩率
            result = subprocess.run([
                '7z', 'a', '-mx=9', '-r',
                output_path,
                os.path.join(source_folder, '*')
            ], check=True, capture_output=True, text=True)

            self.log(f"🗜️ 使用7z CLI压缩完成: {output_path}")
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"❌ 7z压缩失败: {e.stderr}")
            return False
        except Exception as e:
            self.log(f"❌ 7z压缩异常: {str(e)}")
            return False

    def compress_with_py7zr(self, source_folder, output_path):
        """使用py7zr压缩"""
        try:
            with py7zr.SevenZipFile(output_path, 'w', filters=[{"id": py7zr.FILTER_LZMA2}]) as archive:
                # 递归添加文件夹中的所有文件
                for root, dirs, files in os.walk(source_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # 计算相对路径
                        arcname = os.path.relpath(file_path, source_folder)
                        archive.write(file_path, arcname)

            self.log(f"🗜️ 使用py7zr压缩完成: {output_path}")
            return True
        except Exception as e:
            self.log(f"❌ py7zr压缩失败: {str(e)}")
            return False

    def create_gim_file(self, source_folder, output_gim_path, header_path=None):
        """
        创建GIM文件

        参数:
            source_folder: 要压缩的源文件夹路径
            output_gim_path: 输出的GIM文件路径
            header_path: 可选的header文件路径
        """
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_gim_path)
            os.makedirs(output_dir, exist_ok=True)

            # 临时7z文件路径
            temp_7z_path = output_gim_path.replace('.gim', '.7z')

            # 尝试使用7z CLI，如果失败则使用py7zr
            compression_success = False
            if self.has_7z_cli():
                self.log("🧰 使用系统7z CLI进行压缩...")
                compression_success = self.compress_with_7z_cli(source_folder, temp_7z_path)

            if not compression_success:
                self.log("🐍 使用py7zr进行压缩...")
                compression_success = self.compress_with_py7zr(source_folder, temp_7z_path)

            if not compression_success:
                self.log("❌ 压缩失败")
                return False

            # 读取header（如果提供）
            header_data = b''
            if header_path and os.path.exists(header_path):
                with open(header_path, 'rb') as hf:
                    header_data = hf.read(776)
                    if len(header_data) < 776:
                        # 如果header不足776字节，用零填充
                        header_data += b'\x00' * (776 - len(header_data))
            else:
                # 创建默认header（776字节的零）
                header_data = b'\x00' * 776

            # 读取压缩数据
            with open(temp_7z_path, 'rb') as f:
                compressed_data = f.read()

            # 创建GIM文件（header + 压缩数据）
            with open(output_gim_path, 'wb') as outf:
                outf.write(header_data)
                outf.write(compressed_data)

            # 清理临时文件
            if os.path.exists(temp_7z_path):
                os.remove(temp_7z_path)

            self.log(f"✅ GIM文件创建完成: {output_gim_path}")
            return True

        except Exception as e:
            self.log(f"❌ GIM文件创建失败: {str(e)}")
            return False

    def update_and_create_gim(self, extracted_gim_folder, corrected_data, output_gim_path, original_gim_path=None):
        """
        根据校对数据更新CBM文件并创建新的GIM文件

        参数:
            extracted_gim_folder: 解压后的GIM文件夹路径
            corrected_data: 校对后的数据 (DataFrame或字典列表)
            output_gim_path: 输出GIM文件路径
            original_gim_path: 原始GIM文件路径（用于提取header）
        """
        try:
            self.log("🔄 开始更新CBM文件并创建GIM...")

            # 如果输入是DataFrame，转换为字典列表
            if isinstance(corrected_data, pd.DataFrame):
                data_list = corrected_data.to_dict('records')
            else:
                data_list = corrected_data

            cbm_folder = os.path.join(extracted_gim_folder, 'Cbm')
            if not os.path.exists(cbm_folder):
                self.log(f"❌ CBM文件夹不存在: {cbm_folder}")
                return False

            updated_count = 0

            # 遍历校对数据，更新对应的CBM文件
            for data in data_list:
                # 从数据中提取信息
                tower_id = data.get('杆塔编号', '')
                lat = float(data.get('纬度', 0))
                lon = float(data.get('经度', 0))
                height = float(data.get('高度', 0))
                rotation = float(data.get('北方向偏角', 0))
                cbm_path = data.get('CBM路径', '')

                # 如果有CBM路径信息，直接使用
                if cbm_path and os.path.exists(cbm_path):
                    if self.update_cbm_file(cbm_path, lat, lon, height, rotation):
                        updated_count += 1
                else:
                    # 否则根据杆塔编号查找CBM文件
                    possible_cbm_paths = [
                        os.path.join(cbm_folder, f"{tower_id}.cbm"),
                        os.path.join(cbm_folder, f"tower_{tower_id}.cbm"),
                        os.path.join(cbm_folder, f"T{tower_id}.cbm")
                    ]

                    # 也搜索子文件夹
                    for root, dirs, files in os.walk(cbm_folder):
                        for file in files:
                            if file.endswith('.cbm') and tower_id in file:
                                possible_cbm_paths.append(os.path.join(root, file))

                    # 尝试更新找到的CBM文件
                    updated = False
                    for cbm_file_path in possible_cbm_paths:
                        if os.path.exists(cbm_file_path):
                            if self.update_cbm_file(cbm_file_path, lat, lon, height, rotation):
                                updated_count += 1
                                updated = True
                                break

                    if not updated:
                        self.log(f"⚠️ 未找到杆塔 {tower_id} 对应的CBM文件")

            self.log(f"✅ 共更新了 {updated_count} 个CBM文件")

            # 获取原始GIM文件的header
            header_path = None
            if original_gim_path and os.path.exists(original_gim_path):
                # 从原始GIM文件中提取header
                temp_header_path = os.path.join(os.path.dirname(output_gim_path), 'temp_header.bin')
                with open(original_gim_path, 'rb') as f:
                    header_data = f.read(776)
                with open(temp_header_path, 'wb') as f:
                    f.write(header_data)
                header_path = temp_header_path

            # 创建新的GIM文件
            success = self.create_gim_file(extracted_gim_folder, output_gim_path, header_path)

            # 清理临时header文件
            if header_path and os.path.exists(header_path):
                os.remove(header_path)

            if success:
                self.log(f"🎉 校对数据已成功写回并生成新的GIM文件: {output_gim_path}")

            return success

        except Exception as e:
            self.log(f"❌ 更新和创建GIM失败: {str(e)}")
            return False


def update_and_compress_from_correction(extracted_gim_folder, corrected_data, output_gim_path, original_gim_path=None,
                                        log_callback=None):
    """
    便捷函数：从校对数据更新CBM并创建GIM文件

    参数:
        extracted_gim_folder: 解压后的GIM文件夹路径
        corrected_data: 校对后的数据
        output_gim_path: 输出GIM文件路径
        original_gim_path: 原始GIM文件路径
        log_callback: 日志回调函数
    """
    updater = CBMUpdater(log_callback)
    return updater.update_and_create_gim(extracted_gim_folder, corrected_data, output_gim_path, original_gim_path)