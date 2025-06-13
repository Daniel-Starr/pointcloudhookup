import numpy as np
import open3d as o3d
import laspy
import os


def extract_and_visualize_towers(las_path: str, tower_obbs: list):
    """
    根据杆塔OBB信息在点云中可视化杆塔

    参数:
        las_path: LAS点云文件路径
        tower_obbs: 杆塔OBB信息列表，每个元素是一个字典，包含：
            'center': 中心点坐标 [x, y, z]
            'extent': 三个方向的尺寸 [dx, dy, dz]
            'rotation': 3x3旋转矩阵
    """
    if not os.path.exists(las_path):
        raise FileNotFoundError(f"未找到文件: {las_path}")

    # 读取点云
    las = laspy.read(las_path)
    points = np.vstack((las.x, las.y, las.z)).T

    tower_geometries = []
    full_pcd = points

    for tower_info in tower_obbs:
        try:
            # 获取杆塔中心位置和尺寸
            center = tower_info['center']
            expansion_ratio = 1.2  # 放大20%
            extents = tower_info['extent'] * expansion_ratio
            rotation = tower_info['rotation']  # 旋转矩阵

            # 创建OBB
            obb = o3d.geometry.OrientedBoundingBox(center, rotation, extents)

            # 创建线框
            lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb)
            line_points = np.asarray(lineset.points)
            lines = np.asarray(lineset.lines)

            # 构造线段的点对（每两个点构成一条线）
            box_pts = []
            for line in lines:
                box_pts.append(line_points[line[0]])
                box_pts.append(line_points[line[1]])

            # 添加红色线框
            tower_geometries.append((np.array(box_pts), (1.0, 0.0, 0.0)))

        except Exception as e:
            print(f"⚠️ 杆塔可视化失败: {str(e)}")
            continue

    return full_pcd, tower_geometries