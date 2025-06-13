import os
import gc
import math
import numpy as np
import laspy
import trimesh
import pandas as pd
from sklearn.cluster import DBSCAN
from pathlib import Path
from pyproj import Transformer

# 已知杆塔位置（用于调试验证）
KNOWN_TOWERS = [
    # (经度, 纬度, 高度)
    # 添加您已知的杆塔位置作为参考
    # (113.52098652, 28.81479053, 97.065),
    # (113.52057006, 28.81479133, 101.431)
]


def extract_towers(
        input_las_path,
        progress_callback=None,
        log_callback=None,
        eps=8.0,
        min_points=100,  # 提高点数要求
        aspect_ratio_threshold=0.8,
        min_height=15.0,
        max_width=50.0,
        min_width=8
):
    """优化后的杆塔检测函数，解决坐标偏差问题"""
    tower_obbs = []  # 存储杆塔OBB信息
    transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)  # 新增坐标转换器

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
        log("📂📂 读取点云文件...")
        progress(5)
        with laspy.open(input_las_path) as las_file:
            las = las_file.read()

            # 正确转换到实际坐标（考虑缩放和偏移）
            scales = las.header.scales
            offsets = las.header.offsets
            raw_points = np.vstack((
                las.x * scales[0] + offsets[0],
                las.y * scales[1] + offsets[1],
                las.z * scales[2] + offsets[2]
            )).T

            # 记录头文件信息用于保存
            header_info = {
                "scales": scales,
                "offsets": offsets,
                "point_format": las.header.point_format,
                "version": las.header.version
            }

            # 调试输出坐标信息
            log(f"坐标范围: X({np.min(raw_points[:, 0]):.6f}-{np.max(raw_points[:, 0]):.6f})")
            log(f"          Y({np.min(raw_points[:, 1]):.6f}-{np.max(raw_points[:, 1]):.6f})")
            log(f"          Z({np.min(raw_points[:, 2]):.2f}-{np.max(raw_points[:, 2]):.2f})")

            del las
    except Exception as e:
        log(f"⚠️ 文件读取失败: {str(e)}")
        return tower_obbs

    # ==================== 高度过滤优化 ====================
    try:
        log("🔍 执行高度过滤...")
        progress(10)
        z_values = raw_points[:, 2]
        base_height = np.min(z_values) + 1.0  # 使用最低点+1m作为基准
        filtered_indices = z_values > (base_height + 5.0)  # 提高过滤阈值
        filtered_points = raw_points[filtered_indices]
        log(f"✅ 高度过滤完成，基准高度: {base_height:.2f}m, 保留点数: {len(filtered_points)}")
    except Exception as e:
        log(f"⚠️ 高度过滤失败: {str(e)}")
        return tower_obbs

    # ==================== 改进的聚类处理 ====================
    chunk_size = 50000  # 分块尺寸
    overlap_size = 2000  # 重叠区域大小
    chunks = []
    for i in range(0, len(filtered_points), chunk_size - overlap_size):
        start = i
        end = min(len(filtered_points), i + chunk_size)
        chunks.append((start, end))

    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    log(f"\n=== 开始聚类处理 ({len(chunks)}个分块) ===")
    progress(20)

    for i, (start, end) in enumerate(chunks):
        try:
            chunk = filtered_points[start:end]
            log(f"处理分块 {i + 1}/{len(chunks)} ({len(chunk)}点)")

            clustering = DBSCAN(
                eps=eps,
                min_samples=min_points,
                n_jobs=-1,
                algorithm='ball_tree'
            ).fit(chunk)

            chunk_labels = clustering.labels_
            chunk_labels[chunk_labels != -1] += current_label
            all_labels[start:end] = chunk_labels

            if np.any(chunk_labels != -1):
                current_label = np.max(chunk_labels[chunk_labels != -1]) + 1

            progress(20 + int(30 * (i + 1) / len(chunks)))
        except Exception as e:
            log(f"⚠️ 分块聚类失败（块{i}）: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    # ==================== 杆塔检测与去重 ====================
    unique_labels = set(all_labels) - {-1}
    tower_centers = []
    duplicate_threshold = 10.0  # 更严格的去重阈值

    log(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")
    progress(60)

    for label_idx, label in enumerate(unique_labels):
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            if len(cluster_points) < min_points:
                log(f"⚠️ 簇{label} 点数不足 ({len(cluster_points)} < {min_points})")
                continue

            # 计算实际高度（基于高程范围）
            min_z = np.min(cluster_points[:, 2])
            max_z = np.max(cluster_points[:, 2])
            actual_height = max_z - min_z

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 尺寸过滤条件
            width = max(extents[0], extents[1])
            aspect_ratio = actual_height / width

            # 调试信息
            log(f"簇{label} - 高度: {actual_height:.1f}m, 宽度: {width:.1f}m, 高宽比: {aspect_ratio:.1f}")

            if not (
                    actual_height > min_height and min_width < width < max_width and aspect_ratio > aspect_ratio_threshold):
                log(f"  过滤原因: {'高度不足' if actual_height <= min_height else ''} "
                    f"{'宽度越界' if width <= min_width or width >= max_width else ''} "
                    f"{'高宽比不足' if aspect_ratio <= aspect_ratio_threshold else ''}")
                continue

            # 获取OBB中心（已经是全局坐标）
            obb_center = obb.transform[:3, 3]

            # 新增：坐标转换 (CGCS2000 -> WGS84)
            lon, lat = transformer.transform(obb_center[0], obb_center[1])
            converted_center = np.array([lon, lat, obb_center[2]])

            # 计算北方向偏角（改进方法）
            north_angle = calculate_north_angle(obb.transform[:3, :3])

            # 去重检查
            is_duplicate = False
            for existing in tower_centers:
                if np.linalg.norm(converted_center[:2] - existing[:2]) < duplicate_threshold:
                    is_duplicate = True
                    break
            if is_duplicate:
                log(f"⚠️ 跳过重复杆塔{label} (中心距: {np.linalg.norm(converted_center[:2] - existing[:2]):.1f}m)")
                continue

            # 保存杆塔信息（包含转换后的坐标）
            tower_info = {
                "center": converted_center,  # 使用转换后的坐标
                "original_center": obb_center,  # 保留原始坐标
                "rotation": obb.transform[:3, :3],
                "extent": extents,
                "height": actual_height,
                "width": width,
                "north_angle": north_angle
            }
            tower_obbs.append(tower_info)
            tower_centers.append(converted_center)

            # 保存点云
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(cluster_points, None, header_info, output_path, log)

            log(f"✅ 杆塔{label}: {actual_height:.1f}m高 | {width:.1f}m宽 | "
                f"WGS84坐标({lon:.6f}, {lat:.6f}, {obb_center[2]:.2f}) | "
                f"北偏角: {north_angle:.1f}°")

            progress(60 + int(30 * (label_idx + 1) / len(unique_labels)))

        except Exception as e:
            log(f"⚠️ 簇{label} 处理失败: {str(e)}")
            continue
        finally:
            del cluster_points, cluster_pc, obb
            gc.collect()

    # ==================== 基准点验证 ====================
    if KNOWN_TOWERS and tower_obbs:
        log("\n=== 基准点验证 ===")
        for ref_idx, ref in enumerate(KNOWN_TOWERS):
            min_dist = float('inf')
            nearest_height = 0
            for tower in tower_obbs:
                # 使用转换后的WGS84坐标进行比较
                dist = np.sqrt((tower['center'][0] - ref[0]) ** 2 +
                               (tower['center'][1] - ref[1]) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_height = tower['height']
                    nearest_center = tower['center']

            height_diff = abs(nearest_height - ref[2])
            log(f"基准点{ref_idx + 1}({ref[0]:.6f}, {ref[1]:.6f}, {ref[2]:.1f}m): "
                f"最近杆塔距离={min_dist:.2f}m, 高度差={height_diff:.2f}m")
            log(f"    检测位置: ({nearest_center[0]:.6f}, {nearest_center[1]:.6f}, {nearest_center[2]:.1f}m)")

    # ==================== 保存杆塔信息到Excel ====================
    if tower_obbs:
        try:
            output_excel_path = "towers_info.xlsx"
            towers_info = []
            for idx, tower in enumerate(tower_obbs):
                towers_info.append({
                    "ID": idx,
                    "经度": tower['center'][0],  # WGS84经度
                    "纬度": tower['center'][1],  # WGS84纬度
                    "海拔高度": tower['center'][2],
                    "原始X坐标": tower['original_center'][0],  # CGCS2000 X
                    "原始Y坐标": tower['original_center'][1],  # CGCS2000 Y
                    "杆塔高度": tower['height'],
                    "北方向偏角": tower['north_angle'],
                    "宽度": tower['width']
                })

            df = pd.DataFrame(towers_info)
            df.to_excel(output_excel_path, index=False)
            log(f"\n✅ 杆塔信息已保存到: {output_excel_path}")
            log(f"检测到杆塔数量: {len(tower_obbs)}个")
        except Exception as e:
            log(f"⚠️ 保存Excel失败: {str(e)}")
    else:
        log("\n⚠️ 未检测到任何杆塔，不生成Excel文件")

    progress(95)
    log("✅ 杆塔提取完成")
    return tower_obbs


def calculate_north_angle(rotation_matrix):
    """计算杆塔相对于正北方向的偏角（0-360度）"""
    try:
        # 获取垂直方向（假设Z轴向上）
        vertical = np.array([0, 0, 1])

        # 选择水平面上投影最长的轴
        x_proj = np.linalg.norm(rotation_matrix[:2, 0])
        y_proj = np.linalg.norm(rotation_matrix[:2, 1])
        main_axis_idx = 0 if x_proj > y_proj else 1

        # 获取主轴方向
        direction = rotation_matrix[:, main_axis_idx]

        # 投影到水平面
        horizontal_direction = direction - np.dot(direction, vertical) * vertical
        horizontal_direction = horizontal_direction[:2]  # 取XY分量

        # 归一化
        norm = np.linalg.norm(horizontal_direction)
        if norm < 1e-6:
            return 0.0
        horizontal_direction /= norm

        # 计算正北夹角（正北为Y轴正方向）
        # atan2(dx, dy) 因为正北是(0,1)方向
        angle_rad = np.arctan2(horizontal_direction[0], horizontal_direction[1])
        north_angle = np.degrees(angle_rad)

        # 转换为0-360度
        if north_angle < 0:
            north_angle += 360

        return north_angle
    except Exception as e:
        print(f"计算北方向偏角失败: {str(e)}")
        return 0.0


def _save_tower_las(points, colors, header_info, output_path, log_callback=None):
    """优化的LAS保存函数"""
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