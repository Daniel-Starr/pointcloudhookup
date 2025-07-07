# elevation_converter.py
# 椭球高到正高的转换模块

import pyproj
import os
import numpy as np


class ElevationConverter:
    """椭球高到正高的转换器"""

    def __init__(self, region_n_value=25.0):
        """
        初始化转换器
        :param region_n_value: 区域经验N值（默认长沙地区约25米）
        """
        self.region_n_value = region_n_value
        self.transformer = None
        self.init_transformer()

    def init_transformer(self):
        """初始化转换器"""
        try:
            # 尝试使用EGM2008模型
            proj_data_dir = pyproj.datadir.get_data_dir()
            os.environ["PROJ_LIB"] = proj_data_dir

            # 创建转换器
            self.transformer = pyproj.Transformer.from_pipeline(
                "+proj=vgridshift +grids=egm08_25.gtx +multiplier=1"
            )
            print("✅ EGM2008转换器初始化成功")
        except Exception as e:
            print(f"⚠️ EGM2008转换器初始化失败，将使用经验值: {str(e)}")
            self.transformer = None

    def ellipsoid_to_orthometric(self, lat, lon, ellipsoid_height):
        """
        将椭球高转换为正高
        :param lat: 纬度(度)
        :param lon: 经度(度)
        :param ellipsoid_height: 椭球高(米)
        :return: 正高(米)
        """
        try:
            if self.transformer:
                # 使用EGM2008模型
                _, _, ortho_height = self.transformer.transform(lon, lat, ellipsoid_height)
                return ortho_height
            else:
                # 使用区域经验值
                return ellipsoid_height - self.region_n_value
        except Exception as e:
            print(f"高程转换失败，使用经验值: {str(e)}")
            return ellipsoid_height - self.region_n_value

    def convert_batch(self, lat_array, lon_array, ellipsoid_heights):
        """
        批量转换椭球高到正高
        :param lat_array: 纬度数组
        :param lon_array: 经度数组
        :param ellipsoid_heights: 椭球高数组
        :return: 正高数组
        """
        ortho_heights = []
        for lat, lon, h in zip(lat_array, lon_array, ellipsoid_heights):
            ortho_heights.append(self.ellipsoid_to_orthometric(lat, lon, h))
        return np.array(ortho_heights)


# 便捷函数
def convert_elevation(lat, lon, ellipsoid_height, region_n_value=25.0):
    """
    便捷函数：转换单个点的高程
    :param lat: 纬度(度)
    :param lon: 经度(度)
    :param ellipsoid_height: 椭球高(米)
    :param region_n_value: 区域经验N值
    :return: 正高(米)
    """
    converter = ElevationConverter(region_n_value)
    return converter.ellipsoid_to_orthometric(lat, lon, ellipsoid_height)