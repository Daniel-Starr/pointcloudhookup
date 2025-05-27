import re
import os
import laspy
import numpy as np
import open3d as o3d

def create_bbox_lineset(x_min, x_max, y_min, y_max, z_min, z_max):
    corners = [
        [x_min, y_min, z_min], [x_max, y_min, z_min],
        [x_max, y_max, z_min], [x_min, y_max, z_min],
        [x_min, y_min, z_max], [x_max, y_min, z_max],
        [x_max, y_max, z_max], [x_min, y_max, z_max]
    ]
    lines = [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7]
    ]
    box_points = []
    for line in lines:
        box_points.append(corners[line[0]])
        box_points.append(corners[line[1]])
    return np.array(box_points)

def extract_and_visualize_towers(las_path: str, parsed_text: str):
    tower_data = []
    pattern = r'✅ 杆塔(\d+): ([\d.]+)m高 \| ([\d.]+)m宽 \| 中心坐标\[(\d+\.?\d*e?[+-]?\d*) (\d+\.?\d*e?[+-]?\d*) (\d+\.?\d*e?[+-]?\d*)\]'
    for line in parsed_text.strip().split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            tower_data.append({
                'id': int(match.group(1)),
                'height': float(match.group(2)),
                'width': float(match.group(3)),
                'x': float(match.group(4)),
                'y': float(match.group(5)),
                'z': float(match.group(6))
            })

    if not os.path.exists(las_path):
        raise FileNotFoundError(f"未找到文件: {las_path}")

    las = laspy.read(las_path)
    points = np.vstack((las.x, las.y, las.z)).T

    tower_geometries = []
    full_pcd = points

    for tower in tower_data:
        w = tower['width']
        h = tower['height']
        cx, cy, cz = tower['x'], tower['y'], tower['z']

        # 粗略筛选点云范围（加大范围确保完整塔杆）
        x_min, x_max = cx - w, cx + w
        y_min, y_max = cy - w, cy + w
        z_min, z_max = cz - h, cz + h * 2

        mask = (
            (points[:, 0] >= x_min) & (points[:, 0] <= x_max) &
            (points[:, 1] >= y_min) & (points[:, 1] <= y_max) &
            (points[:, 2] >= z_min) & (points[:, 2] <= z_max)
        )
        tower_points = points[mask]

        if tower_points.size > 0:
            # 不传点云，只传线框，去掉绿色点云显示
            # tower_geometries.append((tower_points, np.random.rand(3)))

            # 计算最小有向包围盒(OBB)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(tower_points)

            obb = pcd.get_oriented_bounding_box()
            obb.color = (1.0, 0.0, 0.0)

            lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb)
            line_points = np.asarray(lineset.points)
            lines = np.asarray(lineset.lines)

            # 构造 24 个点的线段对
            box_pts = []
            for line in lines:
                box_pts.append(line_points[line[0]])
                box_pts.append(line_points[line[1]])

            tower_geometries.append((np.array(box_pts), (1.0, 0.0, 0.0)))

    return full_pcd, tower_geometries
