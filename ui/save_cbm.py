import os
import pandas as pd
import py7zr

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EXCEL_PATH = os.path.join(BASE_DIR, "updated_tower_list.xlsx")
CBM_DIR = os.path.join(BASE_DIR, "..", "output_gim", "平江电厂", "Cbm")
PROJECT_DIR = os.path.join(BASE_DIR, "..", "output_gim", "平江电厂")
TEMP_7Z_PATH = os.path.join(PROJECT_DIR, "temp.7z")
OUTPUT_GIM = os.path.join(PROJECT_DIR, "final_output.gim")

# def ensure_directories():
#     """
#     自动创建相关目录（如不存在）
#     """
#     for path in [CBM_DIR, PROJECT_DIR]:
#         os.makedirs(path, exist_ok=True)
#     print("📁 所有必要目录已检查/创建。")

def update_blha_from_excel():
    df = pd.read_excel(EXCEL_PATH)
    updated = 0

    for _, row in df.iterrows():
        cbm_filename = str(row.get("CBM路径")).strip()
        blha = f"{row['纬度']},{row['经度']},{row['高度']},179.000000"
        cbm_path = os.path.join(CBM_DIR, cbm_filename)

        if not os.path.isfile(cbm_path):
            print(f"⚠️ 文件不存在: {cbm_path}")
            continue

        try:
            with open(cbm_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            with open(cbm_path, "w", encoding="utf-8") as f:
                for line in lines:
                    if line.startswith("BLHA="):
                        f.write(f"BLHA={blha}\n")
                        updated += 1
                    else:
                        f.write(line)
        except Exception as e:
            print(f"❌ 写入失败: {cbm_path}, 原因: {e}")

    print(f"✅ 成功更新 {updated} 个 CBM 文件的 BLHA 信息。")

def compress_and_rename_to_gim():
    print("📦 正在压缩整个项目目录为 .7z...")
    with py7zr.SevenZipFile(TEMP_7Z_PATH, 'w') as archive:
        archive.writeall(PROJECT_DIR, arcname='平江电厂')
    print("✅ 压缩完成：", TEMP_7Z_PATH)

    # 重命名为 .gim
    if os.path.exists(OUTPUT_GIM):
        os.remove(OUTPUT_GIM)

    os.rename(TEMP_7Z_PATH, OUTPUT_GIM)
    print(f"🎉 成功生成 GIM 文件：{OUTPUT_GIM}")

def run_save_and_compress(log_fn=print):
    """
    从 GUI 调用的封装函数：更新 CBM 文件中的 BLHA 并压缩整个项目为 .gim。
    参数:
        log_fn: 用于 GUI 日志显示的函数，如 QTextEdit.append 或 print。
    """
    log_fn("🔧 Step 1: 写入 .cbm 文件中的 BLHA 信息...")
    try:
        df = pd.read_excel(EXCEL_PATH)
    except Exception as e:
        log_fn(f"❌ 无法读取 Excel 文件: {e}")
        return

    updated = 0
    for _, row in df.iterrows():
        cbm_filename = str(row.get("CBM路径")).replace("\\", "/").strip()
        blha = f"{row['纬度']},{row['经度']},{row['高度']},179.000000"
        cbm_path = os.path.join(CBM_DIR, cbm_filename)

        if not os.path.isfile(cbm_path):
            log_fn(f"⚠️ 文件不存在: {cbm_path}")
            continue

        try:
            with open(cbm_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            with open(cbm_path, "w", encoding="utf-8") as f:
                for line in lines:
                    if line.startswith("BLHA="):
                        f.write(f"BLHA={blha}\n")
                        updated += 1
                    else:
                        f.write(line)
        except Exception as e:
            log_fn(f"❌ 写入失败: {cbm_path}, 原因: {e}")

    log_fn(f"✅ 成功更新 {updated} 个 CBM 文件的 BLHA 信息。")

    # 压缩
    log_fn("📦 Step 2: 压缩整个项目为 GIM...")
    try:
        if os.path.exists(OUTPUT_GIM):
            os.remove(OUTPUT_GIM)

        with py7zr.SevenZipFile(TEMP_7Z_PATH, 'w') as archive:
            archive.writeall(PROJECT_DIR, arcname='平江电厂')
        os.rename(TEMP_7Z_PATH, OUTPUT_GIM)
        log_fn(f"🎉 成功生成 GIM 文件：{OUTPUT_GIM}")
    except Exception as e:
        log_fn(f"❌ 压缩失败: {e}")


def main():
    # print("🔧 Step 0: 创建所需目录（如不存在）...")
    # ensure_directories()

    print("🔧 Step 1: 写入 .cbm 文件中的 BLHA 信息...")
    update_blha_from_excel()

    print("\n📦 Step 2: 压缩并改名为 .gim 文件...")
    compress_and_rename_to_gim()

    print("\n✅ 全部完成！")

if __name__ == "__main__":
    main()
