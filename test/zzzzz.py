import os
import gc
import math
import numpy as np
import laspy
import trimesh
import pandas as pd
from sklearn.cluster import DBSCAN
from pathlib import Path


def extract_towers(
        input_las_path,
        eps=8.0,
        min_points=50,
        aspect_ratio_threshold=0.8,
        min_height=15.0,
        max_width=50.0,
        min_width=8
):
    """独立运行的杆塔检测函数"""
    # 创建输出目录
    output_dir = Path("../output_towers")
    output_dir.mkdir(exist_ok=True)

    # 打印处理信息
    print(f"📂 开始处理点云文件: {input_las_path}")

    # ==================== 数据读取和预处理 ====================
    try:
        print("📂 读取点云文件...")
        with laspy.open(input_las_path) as las_file:
            las = las_file.read()

            # 转换到实际坐标
            scales = las.header.scales
            offsets = las.header.offsets
            raw_points = np.vstack((
                las.x * scales[0] + offsets[0],
                las.y * scales[1] + offsets[1],
                las.z * scales[2] + offsets[2]
            )).T

            # 记录头文件信息
            header_info = {
                "scales": scales,
                "offsets": offsets,
                "point_format": las.header.point_format,
                "version": las.header.version
            }

            # 打印坐标范围
            print(f"坐标范围: X({np.min(raw_points[:, 0]):.2f}-{np.max(raw_points[:, 0]):.2f})")
            print(f"          Y({np.min(raw_points[:, 1]):.2f}-{np.max(raw_points[:, 1]):.2f})")
            print(f"          Z({np.min(raw_points[:, 2]):.2f}-{np.max(raw_points[:, 2]):.2f})")
    except Exception as e:
        print(f"⚠️ 文件读取失败: {str(e)}")
        return []

    # ==================== 高度过滤优化 ====================
    try:
        print("🔍 执行高度过滤...")
        z_values = raw_points[:, 2]
        base_height = np.min(z_values) + 1.0
        filtered_indices = z_values > (base_height + 5.0)
        filtered_points = raw_points[filtered_indices]
        print(f"✅ 高度过滤完成，保留点数: {len(filtered_points)}")
    except Exception as e:
        print(f"⚠️ 高度过滤失败: {str(e)}")
        return []

    # ==================== 聚类处理 ====================
    print("\n=== 开始聚类处理 ===")
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    # 直接处理整个点云（不再分块）
    try:
        clustering = DBSCAN(
            eps=eps,
            min_samples=min_points,
            n_jobs=-1,
            algorithm='ball_tree'
        ).fit(filtered_points)

        all_labels = clustering.labels_
        unique_labels = set(all_labels) - {-1}
        print(f"✅ 聚类完成，找到 {len(unique_labels)} 个候选簇")
    except Exception as e:
        print(f"⚠️ 聚类失败: {str(e)}")
        return []

    # ==================== 杆塔检测 ====================
    tower_obbs = []
    tower_centers = []
    duplicate_threshold = 10.0

    print(f"\n=== 开始杆塔检测 ===")

    for label in unique_labels:
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            if len(cluster_points) < min_points:
                continue

            # 计算实际高度
            min_z = np.min(cluster_points[:, 2])
            max_z = np.max(cluster_points[:, 2])
            actual_height = max_z - min_z

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 尺寸过滤
            width = max(extents[0], extents[1])
            aspect_ratio = actual_height / width

            if not (
                    actual_height > min_height and min_width < width < max_width and aspect_ratio > aspect_ratio_threshold):
                continue

            # 获取OBB中心
            obb_center = obb.transform[:3, 3]

            # 计算北方向偏角
            north_angle = calculate_north_angle(obb.transform[:3, :3])

            # 去重检查
            is_duplicate = False
            for existing in tower_centers:
                if np.linalg.norm(obb_center - existing) < duplicate_threshold:
                    is_duplicate = True
                    break
            if is_duplicate:
                continue

            # 保存杆塔信息
            tower_info = {
                "center": obb_center,
                "height": actual_height,
                "width": width,
                "north_angle": north_angle
            }
            tower_obbs.append(tower_info)
            tower_centers.append(obb_center)

            # 打印检测结果
            print(f"✅ 杆塔{label}: {actual_height:.1f}m高 × {width:.1f}m宽 | "
                  f"位置({obb_center[0]:.2f}, {obb_center[1]:.2f}, {obb_center[2]:.2f}) | "
                  f"北偏角: {north_angle:.1f}°")

        except Exception as e:
            print(f"⚠️ 簇{label} 处理失败: {str(e)}")
            continue

    # ==================== 保存结果 ====================
    if tower_obbs:
        try:
            # 保存Excel
            output_excel_path = "../towers_info.xlsx"
            towers_info = []
            for idx, tower in enumerate(tower_obbs):
                towers_info.append({
                    "ID": idx,
                    "经度": tower['center'][0],
                    "纬度": tower['center'][1],
                    "海拔高度": tower['center'][2],
                    "杆塔高度": tower['height'],
                    "北方向偏角": tower['north_angle'],
                    "宽度": tower['width']
                })

            df = pd.DataFrame(towers_info)
            df.to_excel(output_excel_path, index=False)
            print(f"\n✅ 杆塔信息已保存到: {output_excel_path}")

            # 保存点云
            for label in unique_labels:
                cluster_mask = (all_labels == label)
                cluster_points = filtered_points[cluster_mask]
                output_path = output_dir / f"tower_{label}.las"
                _save_tower_las(cluster_points, header_info, output_path)

            print(f"✅ 点云文件已保存到: {output_dir}")
        except Exception as e:
            print(f"⚠️ 保存失败: {str(e)}")

    print(f"\n✅ 杆塔提取完成，共检测到 {len(tower_obbs)} 个杆塔")
    return tower_obbs


def calculate_north_angle(rotation_matrix):
    """计算杆塔相对于正北方向的偏角"""
    try:
        # 获取垂直方向
        vertical = np.array([0, 0, 1])

        # 选择水平面上投影最长的轴
        x_proj = np.linalg.norm(rotation_matrix[:2, 0])
        y_proj = np.linalg.norm(rotation_matrix[:2, 1])
        main_axis_idx = 0 if x_proj > y_proj else 1

        # 获取主轴方向
        direction = rotation_matrix[:, main_axis_idx]

        # 投影到水平面
        horizontal_direction = direction - np.dot(direction, vertical) * vertical
        horizontal_direction = horizontal_direction[:2]

        # 归一化
        norm = np.linalg.norm(horizontal_direction)
        if norm < 1e-6:
            return 0.0
        horizontal_direction /= norm

        # 计算正北夹角
        angle_rad = np.arctan2(horizontal_direction[0], horizontal_direction[1])
        north_angle = np.degrees(angle_rad)

        # 转换为0-360度
        if north_angle < 0:
            north_angle += 360

        return north_angle
    except:
        return 0.0


def _save_tower_las(points, header_info, output_path):
    """保存杆塔点云为LAS文件"""
    try:
        header = laspy.LasHeader(
            point_format=header_info["point_format"],
            version=header_info["version"]
        )
        header.scales = header_info["scales"]
        header.offsets = header_info["offsets"]

        las = laspy.LasData(header)
        las.x = points[:, 0].astype(np.float64)
        las.y = points[:, 1].astype(np.float64)
        las.z = points[:, 2].astype(np.float64)
        las.write(output_path)
    except Exception as e:
        print(f"⚠️ 保存失败 {output_path}: {str(e)}")


def main():
    """独立运行的主函数"""
    import argparse

    # 设置命令行参数
    parser = argparse.ArgumentParser(description='杆塔检测工具')
    parser.add_argument('input', type=str, help='输入LAS文件路径')
    parser.add_argument('--eps', type=float, default=8.0, help='DBSCAN聚类半径')
    parser.add_argument('--min_points', type=int, default=100, help='最小聚类点数')
    parser.add_argument('--min_height', type=float, default=15.0, help='最小杆塔高度')
    args = parser.parse_args()

    # 运行杆塔检测
    extract_towers(
        input_las_path=args.input,
        eps=args.eps,
        min_points=args.min_points,
        min_height=args.min_height
    )


if __name__ == "__main__":
    main()