# 参照towers.py更新的tower_extraction.py

import laspy
import numpy as np
import trimesh
from sklearn.cluster import DBSCAN
from pathlib import Path
import gc
import time
import math
import pandas as pd
import open3d as o3d
import os
import warnings

# 配置环境
warnings.filterwarnings("ignore", category=UserWarning, module="trimesh")


def extract_towers(
        input_las_path,
        progress_callback=None,
        log_callback=None,
        # 参照towers.py的参数设置
        eps=8.0,  # 根据场景调整的邻域半径
        min_points=80,  # 适用于密集点云的最小点数
        aspect_ratio_threshold=0.8,  # 高宽比要求
        min_height=15.0,  # 最小高度
        max_width=50.0,  # 最大宽度
        min_width=8,  # 最小宽度
        duplicate_threshold=30.0  # 去重阈值


):
    """
    参照towers.py的杆塔提取算法
    大尺寸杆塔优化检测函数
    """

    tower_obbs = []
    tower_info_list = []

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    def progress(value):
        if progress_callback:
            progress_callback(value)

    output_dir = Path("output_towers")
    output_dir.mkdir(exist_ok=True)

    # ==================== 数据读取和预处理 ====================
    try:
        log("📂 读取点云文件...")
        progress(5)
        with laspy.open(input_las_path) as las_file:
            las = las_file.read()
            raw_points = np.stack([las.x, las.y, las.z], axis=1).astype(np.float32)
            centroid = np.mean(raw_points, axis=0)
            points = raw_points - centroid
            header_info = {
                "scales": las.header.scales,
                "offsets": las.header.offsets,
                "point_format": las.header.point_format,
                "version": las.header.version,
                "centroid": centroid
            }
            del las
            log(f"✅ 点云读取完成，总点数: {len(raw_points)}")
    except Exception as e:
        log(f"⚠️ 文件读取失败: {str(e)}")
        return tower_obbs

    # ==================== 高度过滤优化 ====================
    try:
        log("🔍 执行高度过滤...")
        progress(10)
        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)  # 降低基准高度
        filtered_points = points[z_values > (base_height + 3.0)]  # 提高过滤阈值
        log(f"✅ 高度过滤完成，保留点数: {len(filtered_points)}")

        if len(filtered_points) < 1000:
            log("⚠️ 过滤后点数太少，尝试降低过滤阈值")
            filtered_points = points[z_values > (base_height + 1.0)]

    except Exception as e:
        log(f"⚠️ 高度过滤失败: {str(e)}")
        return tower_obbs

    # ==================== 改进的聚类处理 ====================
    chunk_size = 50000  # 增大分块尺寸
    chunks = [filtered_points[i:i + chunk_size] for i in range(0, len(filtered_points), chunk_size)]
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    log("\n=== 开始聚类处理 ===")
    progress(20)

    for i, chunk in enumerate(chunks):
        try:
            log(f"处理分块 {i + 1}/{len(chunks)} ({len(chunk)}点)")
            clustering = DBSCAN(
                eps=eps,
                min_samples=min_points,
                n_jobs=-1,
                algorithm='ball_tree'  # 使用更高效的算法
            ).fit(chunk)
            chunk_labels = clustering.labels_
            chunk_labels[chunk_labels != -1] += current_label
            all_labels[i * chunk_size:(i + 1) * chunk_size] = chunk_labels
            current_label = np.max(chunk_labels) + 1 if np.any(chunk_labels != -1) else current_label
            progress(20 + int(50 * (i + 1) / len(chunks)))
        except Exception as e:
            log(f"⚠️ 分块聚类失败（块{i}）: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    # ==================== 杆塔检测与去重 ====================
    unique_labels = set(all_labels) - {-1}
    tower_centers = []

    log(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")
    progress(75)

    for label_idx, label in enumerate(unique_labels):
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 尺寸过滤条件 - 使用towers.py的逻辑
            height = extents[2]
            width = max(extents[0], extents[1])
            aspect_ratio = height / width

            if not (height > min_height and min_width < width < max_width and aspect_ratio > aspect_ratio_threshold):
                continue


            # 计算正确全局坐标
            obb_center = obb.transform[:3, 3] + centroid

            # 去重检查 - 使用towers.py的逻辑
            is_duplicate = False
            for existing in tower_centers:
                distance = np.linalg.norm(obb_center - existing)
                if distance < duplicate_threshold:
                    is_duplicate = True
                    log(f"⚠️ 跳过重复杆塔{label} (中心距: {distance:.1f}m)")
                    break
            if is_duplicate:
                continue

            # 计算北方向偏角
            rotation_matrix = obb.transform[:3, :3]
            x_axis = rotation_matrix[:, 0]
            horizontal_direction = np.array([x_axis[0], x_axis[1], 0])
            if np.linalg.norm(horizontal_direction) > 1e-6:
                horizontal_direction /= np.linalg.norm(horizontal_direction)
            else:
                horizontal_direction = np.array([1, 0, 0])

            angle_rad = np.arctan2(horizontal_direction[1], horizontal_direction[0])
            north_angle = np.degrees(angle_rad)
            if north_angle < 0:
                north_angle += 360
            north_angle = (90 - north_angle) % 360

            # 保存杆塔信息
            tower_info = {
                "center": obb_center,
                "rotation": obb.transform[:3, :3],
                "extent": extents,
                "height": height,
                "width": width,
                "north_angle": north_angle,
                "points": cluster_points  # 保存原始点云
            }
            tower_obbs.append(tower_info)
            tower_centers.append(obb_center)

            # 保存到信息列表
            tower_info_list.append({
                "ID": f"tower_{label}",
                "经度": obb_center[0],
                "纬度": obb_center[1],
                "海拔高度": obb_center[2],
                "杆塔高度": height,
                "北方向偏角": north_angle,
                "宽度": width,
                "长宽比": aspect_ratio
            })

            # 保存点云
            original_points = cluster_points + centroid
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(original_points, None, header_info, output_path, log)

            log(f"✅ 杆塔{label}: {height:.1f}m高 | {width:.1f}m宽 | 中心坐标{obb_center}")

            progress(75 + int(15 * (label_idx + 1) / len(unique_labels)))

        except Exception as e:
            log(f"⚠️ 簇{label} 处理失败: {str(e)}")
            continue
        finally:
            del cluster_points, cluster_pc, obb
            gc.collect()

    # ==================== 保存杆塔信息到Excel ====================
    if tower_info_list:
        try:
            output_excel_path = "towers_info.xlsx"
            df = pd.DataFrame(tower_info_list)
            df.to_excel(output_excel_path, index=False)
            log(f"\n✅ 杆塔信息已保存到: {output_excel_path}")
            log(f"检测到杆塔数量: {len(tower_obbs)}个")
        except Exception as e:
            log(f"⚠️ 保存Excel失败: {str(e)}")
    else:
        log("\n⚠️ 未检测到任何杆塔，不生成Excel文件")

    # ==================== 内存清理 ====================
    log("\n=== 清理内存 ===")
    del points, filtered_points
    gc.collect()

    progress(100)
    log("✅ 杆塔提取完成")
    return tower_obbs


def _save_tower_las(points, colors, header_info, output_path, log_callback=None):
    """优化的LAS保存函数 - 参照towers.py"""
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
        if log_callback:
            log_callback(f"保存成功：{output_path}")
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 保存失败 {output_path}: {str(e)}")


def create_obb_geometries(tower_obbs):
    """将杆塔信息转换为Open3D OBB几何体列表 - 参照towers.py"""
    geometries = []
    for tower in tower_obbs:
        try:
            obb_o3d = o3d.geometry.OrientedBoundingBox()
            obb_o3d.center = tower['center']
            obb_o3d.extent = tower['extent']
            obb_o3d.R = tower['rotation']
            obb_mesh = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb_o3d)
            obb_mesh.paint_uniform_color([1, 0, 0])  # 红色
            geometries.append(obb_mesh)
        except Exception as e:
            continue
    return geometries


# 为了兼容原有代码，保留其他可能需要的函数
def extract_towers_optimized(*args, **kwargs):
    """兼容性函数"""
    return extract_towers(*args, **kwargs)


if __name__ == "__main__":
    """测试函数"""
    start_time = time.time()
    try:
        extract_towers(
            input_las_path="E:/pointcloudhookup002/output/point_2.las",
            eps=8.0,  # 根据场景调整
            min_points=80,  # 适用于密集点云
            aspect_ratio_threshold=0.8,
            min_height=15.0,
            max_width=50.0,
            min_width=8
        )
    except Exception as e:
        print(f"⚠️ 程序错误: {str(e)}")
    finally:
        print(f"\n总运行时间: {time.time() - start_time:.1f}秒")