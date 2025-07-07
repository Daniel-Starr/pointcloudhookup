import pandas as pd
from pyproj import Transformer, datadir
import os

# geoid 网格路径
geoid_path = r"D:/anaconda/envs/pointcloudhookup/Library/share/proj/egm96_15.gtx"

print("🔍 当前 pyproj 数据目录:", datadir.get_data_dir())
if os.path.exists(geoid_path):
    print("✅ 找到 EGM96 网格文件：", geoid_path)
else:
    print("❌ 未找到 geoid 网格文件，退出")
    exit(1)

# 示例数据
data = {
    "编号": ["P142", "P143", "P144", "P145"],
    "纬度": [28.379743, 28.376914, 28.373484, 28.369953],
    "经度": [113.363246, 113.364204, 113.365366, 113.366563],
    "椭球高": [104.03, 70.52, 69.68, 67.15]
}
df = pd.DataFrame(data)

# 构建 transformer
transformer = Transformer.from_pipeline(f"""
    +proj=pipeline
    +step +proj=unitconvert +xy_in=deg +xy_out=rad
    +step +proj=vgridshift +grids={geoid_path} +multiplier=-1
""")

# 应用转换
正高 = []
for lon, lat, h in zip(df["经度"], df["纬度"], df["椭球高"]):
    _, _, h_orth = transformer.transform(lon, lat, h)
    正高.append(round(h_orth, 3))

df["正高"] = 正高
df["N值"] = df["椭球高"] - df["正高"]

# 输出
print("\n=== 高程转换结果 ===")
print(df[["编号", "纬度", "经度", "椭球高", "正高", "N值"]])

print("\n=== 统计信息 ===")
print(f"平均椭球高: {df['椭球高'].mean():.2f} 米")
print(f"平均正高: {df['正高'].mean():.2f} 米")
print(f"平均 N 值: {df['N值'].mean():.2f} 米")

if abs(df["N值"].mean()) < 0.1:
    print("\n⚠️ 警告：N 值接近 0，说明网格仍未生效")
else:
    print("\n✅ 网格转换成功！")
