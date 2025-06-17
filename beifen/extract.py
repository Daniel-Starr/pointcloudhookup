import numpy as np
import open3d as o3d
import laspy
import os


def extract_and_visualize_towers(las_path: str, tower_obbs: list,
                                 scale_factors: list = None,
                                 line_color: tuple = (1.0, 0.0, 0.0),
                                 adaptive_scaling: bool = True):
    """
    增强版的杆塔提取和可视化函数

    参数:
        las_path: 点云文件路径
        tower_obbs: 杆塔OBB信息列表
        scale_factors: 放大因子 [x_scale, y_scale, z_scale]
        line_color: 线框颜色 (R, G, B)
        adaptive_scaling: 是否使用自适应缩放

    返回:
        full_pcd: 完整点云数据
        tower_geometries: 增强后的杆塔几何体列表
    """

    # 默认放大因子 - 确保完全包裹杆塔
    if scale_factors is None:
        scale_factors = [2.8, 2.8, 4.5]  # x和y方向放大2.8倍，z方向放大4.5倍（进一步增加高度）

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
                # 自适应缩放：根据杆塔高度调整放大因子 - 进一步增加高度
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


def create_enhanced_tower_boxes(tower_obbs: list,
                                scale_factors: list = None,
                                line_width: float = 3.0,
                                add_center_marker: bool = True):
    """
    创建增强的杆塔边界框

    参数:
        tower_obbs: 杆塔OBB信息列表
        scale_factors: 放大因子
        line_width: 线条宽度
        add_center_marker: 是否添加中心点标记

    返回:
        enhanced_geometries: 增强的几何体列表
    """

    if scale_factors is None:
        scale_factors = [3.2, 3.2, 5.0]  # 更大的放大因子，确保完全包裹

    enhanced_geometries = []

    for i, tower_info in enumerate(tower_obbs):
        try:
            center = tower_info['center']
            rotation = tower_info['rotation']
            original_extents = np.array(tower_info['extent'])

            # 应用放大因子
            enhanced_extents = original_extents * np.array(scale_factors)

            # 创建主要的边界框
            obb = o3d.geometry.OrientedBoundingBox(center, rotation, enhanced_extents)
            lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb)
            line_points = np.asarray(lineset.points)
            lines = np.asarray(lineset.lines)

            # 主边界框线段
            main_box_pts = []
            for line in lines:
                main_box_pts.append(line_points[line[0]])
                main_box_pts.append(line_points[line[1]])

            # 添加主边界框（红色）
            enhanced_geometries.append((np.array(main_box_pts), (1.0, 0.0, 0.0)))

            # 如果需要，添加中心点标记
            if add_center_marker:
                # 创建小的中心标记立方体
                marker_size = min(enhanced_extents) * 0.1
                marker_extents = np.array([marker_size, marker_size, marker_size])
                marker_obb = o3d.geometry.OrientedBoundingBox(center, rotation, marker_extents)
                marker_lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(marker_obb)
                marker_points = np.asarray(marker_lineset.points)
                marker_lines = np.asarray(marker_lineset.lines)

                marker_pts = []
                for line in marker_lines:
                    marker_pts.append(marker_points[line[0]])
                    marker_pts.append(marker_points[line[1]])

                # 添加中心标记（黄色）
                enhanced_geometries.append((np.array(marker_pts), (1.0, 1.0, 0.0)))

            # 可选：添加高度指示线（从地面到顶部的垂直线）
            height_line_pts = []
            base_center = np.array(center)
            base_center[2] = center[2] - enhanced_extents[2] / 2  # 底部中心
            top_center = np.array(center)
            top_center[2] = center[2] + enhanced_extents[2] / 2  # 顶部中心

            height_line_pts.append(base_center)
            height_line_pts.append(top_center)

            # 添加高度指示线（绿色）
            enhanced_geometries.append((np.array(height_line_pts), (0.0, 1.0, 0.0)))

            print(f"✅ 增强杆塔{i}: 原始{original_extents} -> 增强{enhanced_extents}")

        except Exception as e:
            print(f"⚠️ 增强杆塔{i}失败: {str(e)}")
            continue

    return enhanced_geometries


def visualize_towers_with_point_cloud(las_path: str, tower_obbs: list,
                                      output_path: str = None,
                                      scale_factors: list = None):
    """
    可视化杆塔和点云的完整函数

    参数:
        las_path: 点云文件路径
        tower_obbs: 杆塔OBB信息
        output_path: 可选的输出文件路径
        scale_factors: 放大因子
    """

    try:
        # 获取增强的杆塔几何体
        full_pcd, tower_geometries = extract_and_visualize_towers(
            las_path, tower_obbs, scale_factors
        )

        print(f"📊 完整可视化: {len(full_pcd)} 个点, {len(tower_geometries)} 个杆塔")

        # 如果指定了输出路径，可以保存结果
        if output_path:
            try:
                # 这里可以添加保存逻辑
                print(f"💾 结果将保存到: {output_path}")
            except Exception as e:
                print(f"⚠️ 保存失败: {str(e)}")

        return full_pcd, tower_geometries

    except Exception as e:
        print(f"❌ 可视化失败: {str(e)}")
        return None, []


# 提供一些预设的放大方案 - 确保完全包裹杆塔
SCALE_PRESETS = {
    "conservative": [2.2, 2.2, 3.5],  # 保守的放大
    "moderate": [2.8, 2.8, 4.5],  # 中等放大，能包裹大部分杆塔
    "aggressive": [3.2, 3.2, 5.0],  # 激进的放大，确保完全包裹
    "very_large": [3.8, 3.8, 5.5],  # 非常大的放大
    "complete_coverage": [3.2, 3.2, 5.2],  # 完全覆盖方案
    "custom_tall": [2.8, 2.8, 5.8],  # 强调高度的放大
    "custom_wide": [4.5, 4.5, 4.0],  # 强调宽度的放大
    "user_preferred": [2.8, 2.8, 4.5],  # 根据用户反馈的首选方案
    "perfect_wrap": [3.0, 3.0, 5.0],  # 完美包裹方案
}


def get_scale_preset(preset_name: str):
    """获取预设的放大方案"""
    return SCALE_PRESETS.get(preset_name, SCALE_PRESETS["moderate"])


# 使用示例函数
def demo_enhanced_visualization(las_path: str, tower_obbs: list):
    """演示不同放大方案的效果"""

    print("🎨 演示不同放大方案:")

    for preset_name, scale_factors in SCALE_PRESETS.items():
        print(f"\n--- {preset_name.upper()} 方案 (放大因子: {scale_factors}) ---")

        try:
            full_pcd, tower_geometries = extract_and_visualize_towers(
                las_path, tower_obbs, scale_factors
            )
            print(f"✅ {preset_name}: 成功生成 {len(tower_geometries)} 个杆塔")

        except Exception as e:
            print(f"❌ {preset_name}: 失败 - {str(e)}")


if __name__ == "__main__":
    # 测试代码
    print("🧪 extract.py 测试模式")

    # 示例杆塔数据
    example_tower = {
        'center': np.array([100.0, 200.0, 50.0]),
        'rotation': np.eye(3),
        'extent': np.array([5.0, 5.0, 30.0])
    }

    print("📝 示例杆塔信息:")
    print(f"  中心: {example_tower['center']}")
    print(f"  尺寸: {example_tower['extent']}")

    # 测试不同的放大方案
    for preset_name, scale_factors in SCALE_PRESETS.items():
        enhanced_extents = np.array(example_tower['extent']) * np.array(scale_factors)
        print(f"  {preset_name}: {example_tower['extent']} -> {enhanced_extents}")