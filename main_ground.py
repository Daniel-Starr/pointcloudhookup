import numpy as np
import open3d as o3d
from sklearn.linear_model import RANSACRegressor
import laspy
from sklearn.cluster import DBSCAN
# from scipy.spatial import OrientedBoundingBox

def remove_ground_ransac(points, distance_threshold=0.1, max_iterations=1000):
    """
    使用RANSAC算法去除地面点
    :param points: 输入点云(N×3 numpy数组)
    :param distance_threshold: 点到平面的最大距离阈值(米)
    :param max_iterations: RANSAC最大迭代次数
    :return: (非地面点, 地面点)
    """
    # 准备数据：使用xy坐标作为特征，z坐标作为目标值
    X = points[:, :2]  # xy坐标
    y = points[:, 2]  # z坐标

    # 创建RANSAC回归器
    ransac = RANSACRegressor(
        residual_threshold=distance_threshold,
        max_trials=max_iterations
    )
    ransac.fit(X, y)

    # 获取内点(地面点)和外点(非地面点)
    inlier_mask = ransac.inlier_mask_
    ground_points = points[inlier_mask]
    non_ground_points = points[~inlier_mask]

    return non_ground_points, ground_points

def remove_ground_open3d(points, distance_threshold=0.1, ransac_n=3, num_iterations=1000):
    """
    使用Open3D的RANSAC实现去除地面
    :param points: 输入点云(N×3 numpy数组)
    :param distance_threshold: 点到平面的最大距离
    :param ransac_n: 随机采样点数
    :param num_iterations: 迭代次数
    :return: (非地面点, 地面点)
    """
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # 使用RANSAC分割平面
    plane_model, inliers = pcd.segment_plane(
        distance_threshold=distance_threshold,
        ransac_n=ransac_n,
        num_iterations=num_iterations
    )

    # 获取地面点和非地面点
    inlier_cloud = pcd.select_by_index(inliers)
    outlier_cloud = pcd.select_by_index(inliers, invert=True)

    return np.asarray(outlier_cloud.points), np.asarray(inlier_cloud.points)



def visualize_results(ground_points, non_ground_points):
    """可视化结果"""
    # 创建地面点云(红色)
    pcd_ground = o3d.geometry.PointCloud()
    pcd_ground.points = o3d.utility.Vector3dVector(ground_points)
    pcd_ground.paint_uniform_color([1, 0, 0])  # 红色

    # 创建非地面点云(蓝色)
    pcd_non_ground = o3d.geometry.PointCloud()
    pcd_non_ground.points = o3d.utility.Vector3dVector(non_ground_points)
    pcd_non_ground.paint_uniform_color([0, 0, 1])  # 蓝色

    # 可视化
    o3d.visualization.draw_geometries([pcd_ground, pcd_non_ground])


def remove_ground_tiled_ransac(points, tile_size=10.0, **kwargs):
    """
    分块RANSAC地面去除(适用于复杂地形)
    :param points: 输入点云
    :param tile_size: 分块大小(米)
    :param kwargs: 传递给remove_ground_ransac的参数
    :return: (非地面点, 地面点)
    """
    min_xy = np.min(points[:, :2], axis=0)
    max_xy = np.max(points[:, :2], axis=0)

    # 创建分块
    x_edges = np.arange(min_xy[0], max_xy[0], tile_size)
    y_edges = np.arange(min_xy[1], max_xy[1], tile_size)

    non_ground_list = []
    ground_list = []

    for i in range(len(x_edges) - 1):
        for j in range(len(y_edges) - 1):
            # 获取当前分块内的点
            tile_mask = (points[:, 0] >= x_edges[i]) & (points[:, 0] < x_edges[i + 1]) & \
                        (points[:, 1] >= y_edges[j]) & (points[:, 1] < y_edges[j + 1])
            tile_points = points[tile_mask]

            if len(tile_points) < 10:  # 忽略点数太少的块
                continue

            # 对当前分块应用RANSAC
            non_ground, ground = remove_ground_ransac(tile_points, **kwargs)

            non_ground_list.append(non_ground)
            ground_list.append(ground)

    # 合并所有分块结果
    non_ground_points = np.vstack(non_ground_list) if non_ground_list else np.zeros((0, 3))
    ground_points = np.vstack(ground_list) if ground_list else np.zeros((0, 3))

    return non_ground_points, ground_points


def remove_ground(points, height_threshold=4):
    z_values = points[:,2]
    ground_mask = z_values < (np.percentile(z_values, 10) + height_threshold)
    non_ground_mask = z_values >= (np.percentile(z_values, 10) + height_threshold)
    ground_points = points[ground_mask]
    non_ground_points = points[non_ground_mask]
    # percentile_10 = np.percentile(z_values, 10)
    # lower_bound = percentile_10  + 40
    # upper_bound = percentile_10  + 45
    # non_line_mask = (z_values <= lower_bound) | (z_values >= upper_bound)
    # non_ground_line_mask = non_ground_mask & non_line_mask
    # ground_points = points[~non_ground_line_mask]
    # non_ground_points = points[non_ground_line_mask]
    return non_ground_points, ground_points


def process_las_file(input_path, output_path):
    # 1. 读取LAS文件
    las = laspy.read(input_path)
    points = np.vstack((las.x, las.y, las.z)).T

    # 2. 去除地面(选择其中一种方法)
    # non_ground, ground = remove_ground_ransac(points)
    # non_ground, ground = remove_ground_open3d(points)
    # non_ground, ground = remove_ground_tiled_ransac(points, tile_size=20.0)
    non_ground, ground = remove_ground(points)

    # 3. 可视化
    visualize_results(ground, non_ground)

    # 4. 保存非地面点
    save_non_ground_points(las, non_ground, output_path)


def save_non_ground_points(las, non_ground_points, output_path):
    # 创建新的LAS文件只包含非地面点
    header = laspy.LasHeader(point_format=las.header.point_format)
    non_ground_las = laspy.LasData(header)

    # 需要将非地面点转换回原始LAS结构
    # 这里简化处理，实际应用中需要更精确的转换
    non_ground_las.x = non_ground_points[:, 0]
    non_ground_las.y = non_ground_points[:, 1]
    non_ground_las.z = non_ground_points[:, 2]

    # 保存结果
    non_ground_las.write(output_path)
    print(f"已保存非地面点到: {output_path}")


# 使用示例
# process_las_file("output.las", "non_ground_output.las")
process_las_file("pointcloud.las", "non_ground_output.las")