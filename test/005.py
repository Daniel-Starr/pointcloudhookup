import laspy
from pyproj import Transformer
import numpy as np

# 使用原始字符串避免转义问题
las_path = r"E:\pointcloudhookup\output\point_2.las"

# 安全读取文件
try:
    las = laspy.read(las_path)
    crs = las.header.parse_crs()
    print(f"文件坐标系: {crs}")

    if crs is None:
        print("警告：文件未定义坐标系，假设为EPSG:4547")
    elif "4547" not in str(crs):
        print(f"警告：文件坐标系{crs}与预期EPSG:4547不符")

    # 创建转换器
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)

    # 分批处理（内存优化）
    batch_size = 1000000
    for i in range(0, len(las.points), batch_size):
        batch = las.points[i:i + batch_size]
        lon, lat = transformer.transform(batch.x, batch.y)

        # 示例输出第一批数据
        if i == 0:
            print("前5个点转换结果:")
            for j in range(5):
                print(f"原始: {batch.x[j]}, {batch.y[j]} -> 转换后: {lon[j]:.6f}, {lat[j]:.6f}")

except Exception as e:
    print(f"处理失败: {str(e)}")