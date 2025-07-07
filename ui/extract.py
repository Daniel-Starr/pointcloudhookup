import numpy as np
import open3d as o3d
import laspy
import os


def create_bbox_using_kuangxuan_method(center, width, height,
                                       x_left_factor=1.0, x_right_factor=1.67,
                                       y_down_factor=0.5, y_up_factor=1.0,
                                       z_down_factor=1.0, z_up_factor=2.0):
    """
    使用 kuangxuan.py 中的包围盒计算方法

    参数:
        center: 杆塔中心坐标 [x, y, z]
        width: 杆塔宽度
        height: 杆塔高度
        x_left_factor: X方向左侧因子 (默认1.0)
        x_right_factor: X方向右侧因子 (默认1.67，对应 w/0.6)
        y_down_factor: Y方向下方因子 (默认0.5，对应 w/2)
        y_up_factor: Y方向上方因子 (默认1.0)
        z_down_factor: Z方向下方因子 (默认1.0)
        z_up_factor: Z方向上方因子 (默认2.0)

    返回:
        包围盒的 min_coords 和 max_coords
    """
    cx, cy, cz = center

    # 🔧 使用 kuangxuan.py 中的计算方式
    x_min = cx - width * x_left_factor
    x_max = cx + width * x_right_factor
    y_min = cy - width * y_down_factor
    y_max = cy + width * y_up_factor
    z_min = cz - height * z_down_factor
    z_max = cz + height * z_up_factor

    return np.array([x_min, y_min, z_min]), np.array([x_max, y_max, z_max])


def create_bbox_lineset_from_bounds(min_coords, max_coords, color=(1.0, 0.0, 0.0)):
    """
    从边界坐标创建包围盒线框

    参数:
        min_coords: 最小坐标 [x_min, y_min, z_min]
        max_coords: 最大坐标 [x_max, y_max, z_max]
        color: 线框颜色

    返回:
        线框的点对列表，格式为 (points_array, color)
    """
    x_min, y_min, z_min = min_coords
    x_max, y_max, z_max = max_coords

    # 创建8个顶点
    points = [
        [x_min, y_min, z_min], [x_max, y_min, z_min],  # 底面前2个点
        [x_max, y_max, z_min], [x_min, y_max, z_min],  # 底面后2个点
        [x_min, y_min, z_max], [x_max, y_min, z_max],  # 顶面前2个点
        [x_max, y_max, z_max], [x_min, y_max, z_max],  # 顶面后2个点
    ]

    # 定义12条边
    lines = [
        [0, 1], [1, 2], [2, 3], [3, 0],  # 底面4条边
        [4, 5], [5, 6], [6, 7], [7, 4],  # 顶面4条边
        [0, 4], [1, 5], [2, 6], [3, 7]  # 侧面4条边
    ]

    # 构造线段的点对（每两个点构成一条线）
    box_pts = []
    for line in lines:
        box_pts.append(points[line[0]])
        box_pts.append(points[line[1]])

    return np.array(box_pts), color


def extract_and_visualize_towers_kuangxuan(las_path: str, tower_obbs: list,
                                           bbox_method: str = "kuangxuan",
                                           bbox_params: dict = None,
                                           line_color: tuple = (1.0, 0.0, 0.0)):
    """
    使用 kuangxuan.py 方法的增强版杆塔提取和可视化函数

    参数:
        las_path: 点云文件路径
        tower_obbs: 杆塔OBB信息列表
        bbox_method: 包围盒计算方法 ("kuangxuan" 或 "symmetric")
        bbox_params: 包围盒参数字典
        line_color: 线框颜色 (R, G, B)

    返回:
        full_pcd: 完整点云数据
        tower_geometries: 增强后的杆塔几何体列表
    """

    # 默认 kuangxuan 方法参数
    if bbox_params is None:
        bbox_params = {
            "x_left_factor": 1.0,  # 对应原来的 w/1
            "x_right_factor": 1.67,  # 对应原来的 w/0.6
            "y_down_factor": 0.5,  # 对应原来的 w/2
            "y_up_factor": 1.0,  # 对应原来的 w/1
            "z_down_factor": 1.0,  # 对应原来的 h/1
            "z_up_factor": 2.0  # 对应原来的 h*2
        }

    if not os.path.exists(las_path):
        raise FileNotFoundError(f"未找到文件: {las_path}")

    # 读取点云
    las = laspy.read(las_path)
    points = np.vstack((las.x, las.y, las.z)).T

    tower_geometries = []
    full_pcd = points

    print(f"🔧 开始处理 {len(tower_obbs)} 个杆塔，使用方法: {bbox_method}")
    print(f"📊 包围盒参数: {bbox_params}")

    for i, tower_info in enumerate(tower_obbs):
        try:
            # 获取杆塔信息
            center = tower_info['center']
            original_extents = np.array(tower_info['extent'])

            # 从 extent 中提取宽度和高度
            # 假设 extent 为 [x_extent, y_extent, z_extent]
            width = max(original_extents[0], original_extents[1])  # 取较大的水平尺寸作为宽度
            height = original_extents[2]  # Z方向尺寸作为高度

            if bbox_method == "kuangxuan":
                # 🔧 使用 kuangxuan.py 的计算方法
                min_coords, max_coords = create_bbox_using_kuangxuan_method(
                    center, width, height, **bbox_params
                )

                # 计算实际的包围盒尺寸（用于显示）
                actual_x_size = max_coords[0] - min_coords[0]
                actual_y_size = max_coords[1] - min_coords[1]
                actual_z_size = max_coords[2] - min_coords[2]

                print(f"📏 杆塔{i}: 原始宽度{width:.1f}m, 高度{height:.1f}m")
                print(
                    f"📐 杆塔{i}: kuangxuan方法 -> X:{actual_x_size:.1f}m, Y:{actual_y_size:.1f}m, Z:{actual_z_size:.1f}m")

            elif bbox_method == "symmetric":
                # 🔧 可选：对称的包围盒计算方法
                x_scale = bbox_params.get("x_scale", 2.0)
                y_scale = bbox_params.get("y_scale", 2.0)
                z_scale = bbox_params.get("z_scale", 1.5)

                half_x = (width * x_scale) / 2
                half_y = (width * y_scale) / 2
                half_z = (height * z_scale) / 2

                min_coords = center - np.array([half_x, half_y, half_z])
                max_coords = center + np.array([half_x, half_y, half_z])

                print(f"📏 杆塔{i}: 对称方法，缩放因子 X:{x_scale}, Y:{y_scale}, Z:{z_scale}")

            else:
                raise ValueError(f"未知的包围盒方法: {bbox_method}")

            # 创建线框几何体
            box_pts, color = create_bbox_lineset_from_bounds(min_coords, max_coords, line_color)
            tower_geometries.append((box_pts, color))

            print(f"✅ 杆塔{i}处理成功，中心：{center}")

        except Exception as e:
            print(f"⚠️ 杆塔{i}可视化失败: {str(e)}")
            continue

    print(f"✅ 成功处理 {len(tower_geometries)} 个杆塔几何体")
    return full_pcd, tower_geometries


def create_enhanced_tower_boxes_kuangxuan(tower_obbs: list,
                                          bbox_method: str = "kuangxuan",
                                          bbox_params: dict = None,
                                          add_center_marker: bool = True,
                                          add_height_indicator: bool = True):
    """
    使用 kuangxuan 方法创建增强的杆塔边界框

    参数:
        tower_obbs: 杆塔OBB信息列表
        bbox_method: 包围盒计算方法
        bbox_params: 包围盒参数
        add_center_marker: 是否添加中心点标记
        add_height_indicator: 是否添加高度指示线

    返回:
        enhanced_geometries: 增强的几何体列表
    """

    if bbox_params is None:
        bbox_params = {
            "x_left_factor": 1.0, "x_right_factor": 1.67,
            "y_down_factor": 0.5, "y_up_factor": 1.0,
            "z_down_factor": 1.0, "z_up_factor": 2.0
        }

    enhanced_geometries = []

    for i, tower_info in enumerate(tower_obbs):
        try:
            center = tower_info['center']
            original_extents = np.array(tower_info['extent'])

            width = max(original_extents[0], original_extents[1])
            height = original_extents[2]

            # 使用指定方法计算包围盒
            if bbox_method == "kuangxuan":
                min_coords, max_coords = create_bbox_using_kuangxuan_method(
                    center, width, height, **bbox_params
                )
            elif bbox_method == "symmetric":
                x_scale = bbox_params.get("x_scale", 2.0)
                y_scale = bbox_params.get("y_scale", 2.0)
                z_scale = bbox_params.get("z_scale", 1.5)

                half_x = (width * x_scale) / 2
                half_y = (width * y_scale) / 2
                half_z = (height * z_scale) / 2

                min_coords = center - np.array([half_x, half_y, half_z])
                max_coords = center + np.array([half_x, half_y, half_z])

            # 主边界框（红色）
            main_box_pts, _ = create_bbox_lineset_from_bounds(min_coords, max_coords, (1.0, 0.0, 0.0))
            enhanced_geometries.append((main_box_pts, (1.0, 0.0, 0.0)))

            # 中心点标记（黄色小立方体）
            if add_center_marker:
                marker_size = min(width, height) * 0.1
                marker_min = center - np.array([marker_size / 2, marker_size / 2, marker_size / 2])
                marker_max = center + np.array([marker_size / 2, marker_size / 2, marker_size / 2])
                marker_pts, _ = create_bbox_lineset_from_bounds(marker_min, marker_max, (1.0, 1.0, 0.0))
                enhanced_geometries.append((marker_pts, (1.0, 1.0, 0.0)))

            # 高度指示线（绿色垂直线）
            if add_height_indicator:
                base_point = np.array([center[0], center[1], min_coords[2]])
                top_point = np.array([center[0], center[1], max_coords[2]])
                height_line_pts = np.array([base_point, top_point])
                enhanced_geometries.append((height_line_pts, (0.0, 1.0, 0.0)))


        except Exception as e:
            continue

    return enhanced_geometries


# 预设的包围盒参数方案
BBOX_PRESETS = {
    "kuangxuan_original": {  # 原始 kuangxuan.py 参数
        "method": "kuangxuan",
        "params": {
            "x_left_factor": 1.0, "x_right_factor": 1.67,
            "y_down_factor": 0.5, "y_up_factor": 1.0,
            "z_down_factor": 1.0, "z_up_factor": 2.0
        }
    },
    "kuangxuan_conservative": {  # 保守的 kuangxuan 参数
        "method": "kuangxuan",
        "params": {
            "x_left_factor": 0.8, "x_right_factor": 1.2,
            "y_down_factor": 0.4, "y_up_factor": 0.8,
            "z_down_factor": 0.5, "z_up_factor": 1.5
        }
    },
    "kuangxuan_aggressive": {  # 激进的 kuangxuan 参数
        "method": "kuangxuan",
        "params": {
            "x_left_factor": 1.5, "x_right_factor": 2.0,
            "y_down_factor": 0.8, "y_up_factor": 1.5,
            "z_down_factor": 1.5, "z_up_factor": 3.0
        }
    },
    "symmetric_moderate": {  # 对称方法
        "method": "symmetric",
        "params": {
            "x_scale": 2.0, "y_scale": 2.0, "z_scale": 1.5
        }
    },
    "symmetric_large": {  # 大的对称方法
        "method": "symmetric",
        "params": {
            "x_scale": 3.0, "y_scale": 3.0, "z_scale": 2.0
        }
    }
}


def get_bbox_preset(preset_name: str):
    """获取预设的包围盒参数"""
    preset = BBOX_PRESETS.get(preset_name, BBOX_PRESETS["kuangxuan_original"])
    return preset["method"], preset["params"]


def visualize_towers_with_point_cloud_kuangxuan(las_path: str, tower_obbs: list,
                                                preset_name: str = "kuangxuan_original",
                                                output_path: str = None):
    """
    使用 kuangxuan 方法可视化杆塔和点云的完整函数

    参数:
        las_path: 点云文件路径
        tower_obbs: 杆塔OBB信息
        preset_name: 预设参数名称
        output_path: 可选的输出文件路径
    """

    try:
        # 获取预设参数
        bbox_method, bbox_params = get_bbox_preset(preset_name)


        # 获取增强的杆塔几何体
        full_pcd, tower_geometries = extract_and_visualize_towers_kuangxuan(
            las_path, tower_obbs, bbox_method, bbox_params
        )



        if output_path:
            try:
                print(f"💾 结果将保存到: {output_path}")
            except Exception as e:
                print(f"⚠️ 保存失败: {str(e)}")

        return full_pcd, tower_geometries

    except Exception as e:
        print(f"❌ 可视化失败: {str(e)}")
        return None, []


def extract_and_visualize_towers_original(las_path: str, tower_obbs: list,
                                          scale_factors: list = None,
                                          line_color: tuple = (1.0, 0.0, 0.0),
                                          adaptive_scaling: bool = True):
    """
    原始的杆塔提取和可视化函数（使用放大因子方法）
    """

    # 默认放大因子 - 确保完全包裹杆塔
    if scale_factors is None:
        scale_factors = [2.8, 2.8, 4.5]  # x和y方向放大2.8倍，z方向放大4.5倍

    if not os.path.exists(las_path):
        raise FileNotFoundError(f"未找到文件: {las_path}")

    # 读取点云
    las = laspy.read(las_path)
    points = np.vstack((las.x, las.y, las.z)).T

    tower_geometries = []
    full_pcd = points

    print(f"🔧 开始处理 {len(tower_obbs)} 个杆塔，使用放大因子: {scale_factors}")

    for i, tower_info in enumerate(tower_obbs):
        try:
            # 获取杆塔中心位置和尺寸
            center = tower_info['center']
            rotation = tower_info['rotation']  # 旋转矩阵
            original_extents = np.array(tower_info['extent'])

            # 应用自定义放大因子或自适应放大
            if adaptive_scaling:
                # 自适应缩放：根据杆塔高度调整放大因子
                tower_height = original_extents[2]
                if tower_height < 20:  # 低杆塔
                    adaptive_scale = [3.2, 3.2, 5.0]
                elif tower_height < 40:  # 中等杆塔
                    adaptive_scale = [3.0, 3.0, 4.8]
                else:  # 高杆塔
                    adaptive_scale = [2.8, 2.8, 4.5]

                enhanced_extents = original_extents * np.array(adaptive_scale)
                print(f"📏 杆塔{i}: 高度{tower_height:.1f}m, 自适应缩放{adaptive_scale}")
            else:
                # 使用固定放大因子
                enhanced_extents = original_extents * np.array(scale_factors)
                print(f"📏 杆塔{i}: 固定缩放{scale_factors}")

            print(f"📐 杆塔{i}: 原始尺寸{original_extents} -> 增强尺寸{enhanced_extents}")

            # 创建增强的OBB
            obb = o3d.geometry.OrientedBoundingBox(center, rotation, enhanced_extents)

            # 创建线框
            lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb)
            line_points = np.asarray(lineset.points)
            lines = np.asarray(lineset.lines)

            # 构造线段的点对（每两个点构成一条线）
            box_pts = []
            for line in lines:
                box_pts.append(line_points[line[0]])
                box_pts.append(line_points[line[1]])

            # 添加指定颜色的线框
            tower_geometries.append((np.array(box_pts), line_color))

            print(f"✅ 杆塔{i}处理成功，中心：{center}")

        except Exception as e:
            print(f"⚠️ 杆塔{i}可视化失败: {str(e)}")
            continue

    print(f"✅ 成功处理 {len(tower_geometries)} 个杆塔几何体")
    return full_pcd, tower_geometries


def extract_and_visualize_towers(las_path: str, tower_obbs: list,
                                 scale_factors: list = None,
                                 line_color: tuple = (1.0, 0.0, 0.0),
                                 adaptive_scaling: bool = True,
                                 use_kuangxuan_method: bool = True,
                                 kuangxuan_preset: str = "kuangxuan_original"):
    """
    统一的杆塔提取和可视化函数，可选择使用 kuangxuan 方法或原始方法

    参数:
        las_path: 点云文件路径
        tower_obbs: 杆塔OBB信息列表
        scale_factors: 放大因子（原始方法用）
        line_color: 线框颜色
        adaptive_scaling: 是否使用自适应缩放（原始方法用）
        use_kuangxuan_method: 是否使用 kuangxuan 方法
        kuangxuan_preset: kuangxuan 方法的预设名称
    """

    if use_kuangxuan_method:
        # 使用 kuangxuan 方法
        bbox_method, bbox_params = get_bbox_preset(kuangxuan_preset)
        return extract_and_visualize_towers_kuangxuan(
            las_path, tower_obbs, bbox_method, bbox_params, line_color
        )
    else:
        # 使用原始方法
        return extract_and_visualize_towers_original(
            las_path, tower_obbs, scale_factors, line_color, adaptive_scaling
        )


if __name__ == "__main__":
    # 测试代码
    print("🧪 改进的 extract.py 测试模式")

    # 示例杆塔数据
    example_tower = {
        'center': np.array([437587.898, 3140691.58, 131.457]),
        'rotation': np.eye(3),
        'extent': np.array([20.1, 20.1, 17.4])  # 宽度20.1m, 高度17.4m
    }

    print("📝 示例杆塔信息:")
    print(f"  中心: {example_tower['center']}")
    print(f"  尺寸: {example_tower['extent']}")

    # 测试不同的预设方案
    print("\n🎨 测试不同包围盒方案:")
    for preset_name in BBOX_PRESETS.keys():
        method, params = get_bbox_preset(preset_name)
        print(f"\n--- {preset_name.upper()} ---")
        print(f"方法: {method}")
        print(f"参数: {params}")

        if method == "kuangxuan":
            min_coords, max_coords = create_bbox_using_kuangxuan_method(
                example_tower['center'], 20.1, 17.4, **params
            )
            x_size = max_coords[0] - min_coords[0]
            y_size = max_coords[1] - min_coords[1]
            z_size = max_coords[2] - min_coords[2]
            print(f"包围盒尺寸: X={x_size:.1f}m, Y={y_size:.1f}m, Z={z_size:.1f}m")