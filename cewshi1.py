import pyproj
import pandas as pd
import os
import requests
import shutil


def install_egm2008_grid(proj_data_dir):
    """安装EGM2008网格文件（gtx 和 tif）到 PROJ 数据目录"""
    filenames = ["egm08_25.gtx", "egm08_25.tif"]
    if all(os.path.exists(os.path.join(proj_data_dir, f)) for f in filenames):
        print("✔ EGM2008 网格文件已存在")
        return True

    print("🔄 正在下载 EGM2008 网格文件...")
    try:
        temp_dir = "proj_data_temp"
        os.makedirs(temp_dir, exist_ok=True)
        urls = [
            "https://download.osgeo.org/proj/vdatum/egm08_25/egm08_25.gtx",
            "https://download.osgeo.org/proj/vdatum/egm08_25/egm08_25.tif"
        ]
        for url in urls:
            filename = os.path.basename(url)
            response = requests.get(url, stream=True)
            with open(os.path.join(temp_dir, filename), 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        for f in os.listdir(temp_dir):
            shutil.copy2(os.path.join(temp_dir, f), os.path.join(proj_data_dir, f))
        shutil.rmtree(temp_dir)
        print("✅ 网格文件安装完成")
        return True
    except Exception as e:
        print(f"❌ 下载或复制失败: {e}")
        return False


def convert_to_orthometric(lat, lon, ellipsoidal_height, proj_data_dir):
    """使用 gtx 网格文件执行正高转换"""
    try:
        os.environ["PROJ_LIB"] = proj_data_dir
        transformer = pyproj.Transformer.from_pipeline(
            "+proj=vgridshift +grids=egm08_25.gtx +multiplier=1"
        )
        _, _, ortho_height = transformer.transform(lon, lat, ellipsoidal_height)
        return ortho_height
    except Exception as e:
        print(f"转换失败: {e}")
        return ellipsoidal_height


def main():
    # 获取 proj 路径
    proj_data_dir = pyproj.datadir.get_data_dir()
    print(f"pyproj版本: {pyproj.__version__}")
    print(f"PROJ数据路径: {proj_data_dir}")

    # 检查网格文件
    install_egm2008_grid(proj_data_dir)

    # 示例数据
    data = [
        {"杆塔编号": "P142", "纬度": 28.379751, "经度": 113.363246, "椭球高": 131.46},
        {"杆塔编号": "P144", "纬度": 28.373584, "经度": 113.365316, "椭球高": 87.77},
        {"杆塔编号": "P145", "纬度": 28.369979, "经度": 113.366579, "椭球高": 80.06},
        {"杆塔编号": "P143", "纬度": 28.376940, "经度": 113.364167, "椭球高": 82.56}
    ]
    df = pd.DataFrame(data)

    # 计算正高
    df["正高"] = df.apply(lambda r: convert_to_orthometric(
        r["纬度"], r["经度"], r["椭球高"], proj_data_dir), axis=1)
    df["N值"] = df["椭球高"] - df["正高"]

    # 输出结果
    print("\n=== 高程转换结果 ===")
    print(df[["杆塔编号", "纬度", "经度", "椭球高", "正高", "N值"]].to_string(index=False, float_format="%.3f"))

    print("\n=== 统计信息 ===")
    print(f"平均椭球高: {df['椭球高'].mean():.2f} 米")
    print(f"平均正高: {df['正高'].mean():.2f} 米")
    print(f"平均 N 值: {df['N值'].mean():.2f} 米")

    if abs(df['N值'].mean()) < 1:
        print("\n⚠️ 警告: N 值接近 0，转换可能未生效。请检查 PROJ 设置和网格文件是否有效。")

    print("\n✅ 处理完成！")


if __name__ == "__main__":
    main()
