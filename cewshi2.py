import pyproj
import pandas as pd
import numpy as np
import os
import requests
import zipfile
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import shutil


# =====================
# 0. 设置中文字体
# =====================
def set_chinese_font():
    """设置中文字体支持"""
    try:
        # 尝试使用系统自带的中文字体
        plt.rcParams['font.family'] = ['sans-serif']
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'KaiTi']
        plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号
    except Exception as e:
        print(f"字体设置警告: {str(e)}")


# 设置中文字体
set_chinese_font()


# =====================
# 1. 检查并安装EGM2008网格文件
# =====================
def install_egm2008_grid(proj_data_dir):
    """安装EGM2008网格文件到PROJ数据目录"""
    # 检查是否已存在网格文件
    grid_files = ["egm08_25.gtx", "egm08_25.gtx"]
    if all(os.path.exists(os.path.join(proj_data_dir, f)) for f in grid_files):
        print("EGM2008网格文件已存在")
        return True

    print("检测到缺少EGM2008网格文件，正在下载并安装...")

    try:
        # 创建临时目录
        temp_dir = "proj_data_temp"
        os.makedirs(temp_dir, exist_ok=True)

        # 下载网格文件
        grid_urls = [
            "https://download.osgeo.org/proj/vdatum/egm08_25/egm08_25.gtx",
            "https://download.osgeo.org/proj/vdatum/egm08_25/egm08_25.tif"
        ]

        for url in grid_urls:
            filename = os.path.basename(url)
            filepath = os.path.join(temp_dir, filename)

            print(f"正在下载 {filename}...")
            response = requests.get(url, stream=True)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        # 复制到PROJ数据目录
        for filename in os.listdir(temp_dir):
            src = os.path.join(temp_dir, filename)
            dst = os.path.join(proj_data_dir, filename)
            shutil.copy2(src, dst)
            print(f"已安装 {filename} 到 PROJ 数据目录")

        # 清理临时目录
        shutil.rmtree(temp_dir)
        print("EGM2008网格文件安装完成!")
        return True

    except Exception as e:
        print(f"网格文件安装失败: {str(e)}")
        return False


# =====================
# 2. 可靠的高程转换函数
# =====================
def convert_to_orthometric(lat, lon, ellipsoidal_height, proj_data_dir):
    """
    使用EGM2008全球重力模型将椭球高转换为正高
    :param lat: 纬度(度)
    :param lon: 经度(度)
    :param ellipsoidal_height: 椭球高(米)
    :param proj_data_dir: PROJ数据目录
    :return: 正高(米)
    """
    try:
        # 方法1：使用直接网格转换
        try:
            # 设置PROJ网格文件路径
            os.environ["PROJ_LIB"] = proj_data_dir

            # 创建转换器
            transformer = pyproj.Transformer.from_pipeline(
                f"+proj=vgridshift +grids=egm08_25.gtx +multiplier=1"
            )

            # 执行转换
            _, _, ortho_height = transformer.transform(lon, lat, ellipsoidal_height)
            return ortho_height
        except Exception as e:
            print(f"直接网格转换方法失败: {str(e)}")

    #     # 方法2：使用CRS对象
    #     try:
    #         crs_wgs84 = pyproj.CRS("EPSG:4326")
    #         crs_egm2008 = pyproj.CRS("EPSG:4326+3855")
    #         transformer = pyproj.Transformer.from_crs(crs_wgs84, crs_egm2008)
    #         _, _, ortho_height = transformer.transform(lon, lat, ellipsoidal_height)
    #         return ortho_height
    #     except Exception as e:
    #         print(f"CRS对象方法失败: {str(e)}")
    #
    #     # 方法3：使用区域经验值
    #     print("使用长沙地区经验值转换")
    #     return ellipsoidal_height - 25.0  # 长沙地区经验值
    #
    except Exception as e:
        print(f"高程转换错误: {str(e)}")
        return ellipsoidal_height


# =====================
# 3. 主程序
# =====================
def main():
    # 获取PROJ数据目录
    try:
        proj_data_dir = pyproj.datadir.get_data_dir()
        print(f"pyproj版本: {pyproj.__version__}")
        print(f"PROJ数据路径: {proj_data_dir}")
    except:
        # 默认PROJ数据目录
        proj_data_dir = os.path.join(os.path.dirname(__file__), "proj_data")
        os.makedirs(proj_data_dir, exist_ok=True)
        print(f"使用默认PROJ数据路径: {proj_data_dir}")

    # 安装EGM2008网格文件
    grid_installed = install_egm2008_grid(proj_data_dir)

    # 点云数据
    point_cloud_data = [
        {"杆塔编号": "P142", "纬度": 28.379751, "经度": 113.363246, "椭球高": 131.46},
        {"杆塔编号": "P144", "纬度": 28.373584, "经度": 113.365316, "椭球高": 87.77},
        {"杆塔编号": "P145", "纬度": 28.369979, "经度": 113.366579, "椭球高": 80.06},
        {"杆塔编号": "P143", "纬度": 28.376940, "经度": 113.364167, "椭球高": 82.56}
    ]

    # 创建DataFrame
    df = pd.DataFrame(point_cloud_data)

    # 应用高程转换
    df["正高"] = df.apply(lambda row: convert_to_orthometric(
        row["纬度"], row["经度"], row["椭球高"], proj_data_dir), axis=1)

    # 计算大地水准面差距
    df["N值"] = df["椭球高"] - df["正高"]

    # 输出结果
    print("\n转换结果:")
    print(df[["杆塔编号", "纬度", "经度", "椭球高", "正高", "N值"]])

    # 保存到CSV
    output_file = "高程转换结果.csv"
    df.to_csv(output_file, index=False, float_format="%.3f")
    print(f"\n结果已保存至: {output_file}")

    # 结果可视化
    try:
        # 创建结果目录
        os.makedirs("output_plots", exist_ok=True)

        # 高程比较图
        plt.figure(figsize=(10, 6))
        plt.bar(df["杆塔编号"], df["椭球高"], width=0.4, label='椭球高')
        plt.bar([x + 0.4 for x in range(len(df))], df["正高"], width=0.4, label='正高')
        plt.xlabel('杆塔编号')
        plt.ylabel('高程 (米)')
        plt.title('椭球高与正高比较')
        plt.legend()
        plt.tight_layout()
        plt.savefig("output_plots/高程比较图.png")
        print("已生成高程比较图: output_plots/高程比较图.png")

        # N值分布图
        plt.figure(figsize=(8, 5))
        plt.bar(df["杆塔编号"], df["N值"], color='green')
        plt.xlabel('杆塔编号')
        plt.ylabel('N值 (米)')
        plt.title('大地水准面差距 (N值)')
        plt.tight_layout()
        plt.savefig("output_plots/N值分布图.png")
        print("已生成N值分布图: output_plots/N值分布图.png")

        # 关闭所有图形
        plt.close('all')

    except Exception as e:
        print(f"可视化错误: {str(e)}")

    # 生成报告
    try:
        report_file = "高程转换报告.txt"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            f.write("        全球高程基准转换结果报告\n")
            f.write("=" * 50 + "\n\n")

            f.write(f"处理时间: {pd.Timestamp.now()}\n")
            f.write(f"处理点数: {len(df)}\n")
            f.write(f"pyproj版本: {pyproj.__version__}\n")
            f.write(f"PROJ数据目录: {proj_data_dir}\n")
            f.write(f"网格文件状态: {'已安装' if grid_installed else '安装失败'}\n\n")

            f.write("-" * 50 + "\n")
            f.write("转换结果统计:\n")
            f.write("-" * 50 + "\n")
            f.write(f"平均椭球高: {df['椭球高'].mean():.2f} 米\n")
            f.write(f"平均正高: {df['正高'].mean():.2f} 米\n")
            f.write(f"平均N值: {df['N值'].mean():.2f} 米\n\n")

            f.write("-" * 50 + "\n")
            f.write("详细转换结果:\n")
            f.write("-" * 50 + "\n")
            f.write(df.to_string(index=False, float_format="%.3f"))
            f.write("\n\n")

            if df['N值'].mean() < 1:
                f.write("警告: 转换结果异常，N值接近于零!\n")
                f.write("可能原因:\n")
                f.write("1. EGM2008网格文件未正确安装\n")
                f.write("2. PROJ数据目录设置不正确\n")
                f.write("3. 转换方法未正确执行\n\n")

            f.write("=" * 50 + "\n")
            f.write("报告结束\n")
            f.write("=" * 50 + "\n")

        print(f"已生成报告: {report_file}")

    except Exception as e:
        print(f"报告生成错误: {str(e)}")

    print("\n处理完成!")


if __name__ == "__main__":
    main()