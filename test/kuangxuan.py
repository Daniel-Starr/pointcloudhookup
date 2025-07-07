import re
import laspy
import numpy as np
import open3d as o3d


def create_bbox_lineset(x_min, x_max, y_min, y_max, z_min, z_max, color):
    """创建包围盒线框的可视化对象"""
    points = [
        [x_min, y_min, z_min], [x_max, y_min, z_min],
        [x_max, y_max, z_min], [x_min, y_max, z_min],
        [x_min, y_min, z_max], [x_max, y_min, z_max],
        [x_max, y_max, z_max], [x_min, y_max, z_max],
    ]
    lines = [
        [0, 1], [1, 2], [2, 3], [3, 0],  # 底面
        [4, 5], [5, 6], [6, 7], [7, 4],  # 顶面
        [0, 4], [1, 5], [2, 6], [3, 7]  # 侧面连接线
    ]
    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(points)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.paint_uniform_color(color)
    return line_set


# 解析杆塔信息
tower_data = []
input_data = """=== 开始杆塔检测（候选簇：303个） ===
✅ 杆塔8: 17.4m高 | 20.1m宽 | 中心坐标[4.37587898e+05 3.14069158e+06 1.31457350e+02]
✅ 杆塔188: 29.8m高 | 10.2m宽 | 中心坐标[4.37787178e+05 3.14000696e+06 8.77722064e+01]
✅ 杆塔199: 21.8m高 | 16.6m宽 | 中心坐标[4.37908948e+05 3.13960682e+06 8.00563301e+01]
✅ 杆塔235: 21.0m高 | 13.0m宽 | 中心坐标[4.37676583e+05 3.14037950e+06 8.25588932e+01]"""

pattern = r'✅ 杆塔(\d+): ([\d.]+)m高 \| ([\d.]+)m宽 \| 中心坐标\[([\d.e+]+) ([\d.e+]+) ([\d.e+]+)\]'
for line in input_data.split('\n'):
    if match := re.match(pattern, line.strip()):
        tower_data.append({
            'id': int(match.group(1)),
            'height': float(match.group(2)),
            'width': float(match.group(3)),
            'x': float(match.group(4)),
            'y': float(match.group(5)),
            'z': float(match.group(6))
        })

# 读取LAS点云文件
las = laspy.read("E:\pointcloudhookup002\output\point_2.las")
points = np.vstack((las.x, las.y, las.z)).transpose()

# 创建可视化对象集合
visual_objects = []

# 添加完整点云（带透明度）
full_pcd = o3d.geometry.PointCloud()
full_pcd.points = o3d.utility.Vector3dVector(points)
full_pcd.paint_uniform_color([1, 1, 1])  # 灰色背景点云
visual_objects.append(full_pcd)

for tower in tower_data:
    # 计算包围盒参数（修改高度计算部分）
    w = tower['width']
    original_h = tower['height']  # 原始高度
    extended_h = original_h * 2  # 扩展后的高度

    cx, cy, cz = tower['x'], tower['y'], tower['z']

    # 三维包围盒范围计算（高度方向扩展）
    x_min, x_max = cx - w / 1, cx + w / 0.6
    y_min, y_max = cy - w / 2, cy + w / 1
    z_min, z_max = cz - original_h / 1, cz + original_h * 2  # 关键修改点

    # 点云筛选
    mask = (
            (points[:, 0] >= x_min) & (points[:, 0] <= x_max) &
            (points[:, 1] >= y_min) & (points[:, 1] <= y_max) &
            (points[:, 2] >= z_min) & (points[:, 2] <= z_max)
    )
    tower_points = points[mask]

    # 创建高亮点云对象
    if tower_points.size > 0:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(tower_points)
        color = np.random.rand(3)  # 随机鲜艳颜色
        pcd.paint_uniform_color(color)
        visual_objects.append(pcd)

        # 创建包围盒线框
        bbox = create_bbox_lineset(x_min, x_max, y_min, y_max, z_min, z_max, color)
        visual_objects.append(bbox)

# 可视化设置
vis = o3d.visualization.Visualizer()
vis.create_window(window_name="完整点云与杆塔可视化", width=1600, height=900)

# 添加所有几何体
for obj in visual_objects:
    vis.add_geometry(obj)

# 配置渲染选项
opt = vis.get_render_option()
opt.background_color = np.asarray([0.1, 0.1, 0.1])  # 深色背景
opt.point_size = 1.5  # 减小背景点云大小
opt.light_on = True

# 设置初始视角
ctr = vis.get_view_control()
ctr.set_zoom(0.8)

vis.run()
vis.destroy_window()