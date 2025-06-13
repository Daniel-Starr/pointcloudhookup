# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

import laspy
from pyproj import Transformer


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    las = laspy.read("E:\pointcloudhookup\output\point_2.las")
    print("坐标系信息:", las.header.parse_crs())  # 输出EPSG代码或PROJ字符串，查询坐标系
    x, y, z = las.x, las.y, las.z  # 原始坐标（可能是投影坐标）
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)  # 从CGCS2000转WGS84
    lon, lat = transformer.transform(x, y) #注意输入输出顺序， 经度，纬度
    print(lon, lat)

