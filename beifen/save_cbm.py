import pandas as pd
import shutil
import os

# 读取 Excel 文件
def read_excel(file_path):
    """读取 Excel 文件并返回 DataFrame"""
    df = pd.read_excel(file_path)
    return df

# 更新 .cbm 文件中的 BLHA 行
def update_cbm_file(cbm_file_path, lat, lon, height, rotation):
    """更新 .cbm 文件中的 BLHA 行"""
    # 读取现有的 .cbm 文件
    with open(cbm_file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    # 更新 BLHA 行
    new_blha_line = f"BLHA={lat:.6f},{lon:.6f},{height:.3f},{rotation:.3f}\n"
    updated_lines = []
    for line in lines:
        if line.startswith('BLHA='):
            updated_lines.append(new_blha_line)  # 替换 BLHA 行
        else:
            updated_lines.append(line)  # 保持其他行不变

    # 写入更新后的内容到 .cbm 文件
    with open(cbm_file_path, 'w', encoding='utf-8') as file:
        file.writelines(updated_lines)
    print(f"CBM 文件更新成功: {cbm_file_path}")

# 压缩整个“平江电厂”文件夹
def compress_folder(folder_path):
    """将文件夹进行压缩"""
    # 获取上一级文件夹路径
    parent_folder = os.path.dirname(folder_path)
    compressed_file_path = os.path.join(parent_folder, os.path.basename(folder_path) + '.zip')

    # 压缩整个文件夹
    shutil.make_archive(compressed_file_path.replace('.zip', ''), 'zip', folder_path)

    print(f"文件夹压缩完成: {compressed_file_path}")

# 处理并更新文件夹中的所有 .cbm 文件
def process_and_compress_folder(cbm_folder, tower_data_df):
    """更新文件夹中所有 .cbm 文件并进行压缩"""
    # 从 Excel 数据中提取纬度、经度、高度和方向角
    lat = tower_data_df['纬度'][0]  # 假设从第一行获取数据
    lon = tower_data_df['经度'][0]
    height = tower_data_df['高度'][0]
    rotation = tower_data_df['北方向偏角'][0]

    # 检查文件夹是否存在，如果不存在则创建
    if not os.path.exists(cbm_folder):
        print(f"文件夹 {cbm_folder} 不存在，正在创建...")
        os.makedirs(cbm_folder)

    # 遍历文件夹中的所有 .cbm 文件
    for root, dirs, files in os.walk(cbm_folder):
        for file in files:
            if file.endswith('.cbm'):
                cbm_file_path = os.path.join(root, file)
                update_cbm_file(cbm_file_path, lat, lon, height, rotation)

    # 获取“平江电厂”文件夹的路径
    project_folder = os.path.dirname(cbm_folder)  # 获取到“平江电厂”文件夹路径

    # 检查“平江电厂”文件夹是否存在，如果不存在则创建
    if not os.path.exists(project_folder):
        print(f"文件夹 {project_folder} 不存在，正在创建...")
        os.makedirs(project_folder)

    # 压缩整个“平江电厂”文件夹
    compress_folder(project_folder)

# 主程序
if __name__ == "__main__":
    # Excel 文件路径
    excel_file_path = 'E:/pointcloudhookup/tower_data.xlsx'

    # 读取 Excel 数据
    df = read_excel(excel_file_path)

    # .cbm 文件所在文件夹路径（需要根据您的实际情况修改）
    cbm_folder = 'E:/pointcloudhookup/output_gim/平江电厂/Cbm'

    # 处理并压缩文件夹中的所有 .cbm 文件
    process_and_compress_folder(cbm_folder, df)
