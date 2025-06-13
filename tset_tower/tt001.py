# 参照towers.py更新的tower_extraction.py - 优化完整版

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
import psutil  # 用于内存监控

# 配置环境
warnings.filterwarnings("ignore", category=UserWarning, module="trimesh")


def extract_towers(
        input_las_path,
        progress_callback=None,
        log_callback=None,
        # 参数设置
        eps=8.0,  # 邻域半径
        min_points=80,  # 最小点数
        aspect_ratio_threshold=0.8,  # 高宽比要求
        min_height=15.0,  # 最小高度
        max_width=50.0,  # 最大宽度
        min_width=8,  # 最小宽度
        duplicate_threshold=30.0,  # 去重阈值
        strict_duplicate_threshold=2.0  # 严格重复阈值
):
    """
    优化的杆塔提取算法
    主要改进：
    1. 严格去重逻辑（2米内视为同一位置）
    2. 综合质量指标（高度×宽度×点数对数）
    3. 点云范围诊断
    4. 内存使用监控
    5. 结果验证
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

    # 记录内存使用
    def log_memory_usage(stage):
        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / (1024 ** 2)  # MB
        log(f"💾 内存使用({stage}): {mem:.1f} MB")

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

            # 添加点云范围诊断
            log(f"点云范围: X({np.min(raw_points[:, 0]):.2f}-{np.max(raw_points[:, 0]):.2f})")
            log(f"        Y({np.min(raw_points[:, 1]):.2f}-{np.max(raw_points[:, 1]):.2f})")
            log(f"        Z({np.min(raw_points[:, 2]):.2f}-{np.max(raw_points[:, 2]):.2f})")

            log_memory_usage("读取点云后")
    except Exception as e:
        log(f"⚠️ 文件读取失败: {str(e)}")
        return tower_obbs

    # 记录使用参数
    log(f"参数设置: eps={eps}, min_points={min_points}, aspect_ratio_threshold={aspect_ratio_threshold}")
    log(f"         min_height={min_height}, max_width={max_width}, min_width={min_width}")
    log(f"         duplicate_threshold={duplicate_threshold}, strict_duplicate_threshold={strict_duplicate_threshold}")

    # ==================== 高度过滤优化 ====================
    try:
        log("🔍 执行高度过滤...")
        progress(10)
        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)  # 降低基准高度
        filtered_points = points[z_values > (base_height + 3.0)]  # 提高过滤阈值
        log(f"✅ 高度过滤完成，保留点数: {len(filtered_points)}")

        # 添加过滤后范围诊断
        if len(filtered_points) > 0:
            log(f"过滤后点云范围: X({np.min(filtered_points[:, 0]):.2f}-{np.max(filtered_points[:, 0]):.2f})")
            log(f"              Y({np.min(filtered_points[:, 1]):.2f}-{np.max(filtered_points[:, 1]):.2f})")
            log(f"              Z({np.min(filtered_points[:, 2]):.2f}-{np.max(filtered_points[:, 2]):.2f})")
        else:
            log("⚠️ 高度过滤后无点云")

        if len(filtered_points) < 1000:
            log("⚠️ 过滤后点数太少，尝试降低过滤阈值")
            filtered_points = points[z_values > (base_height + 1.0)]
            log(f"新过滤后点数: {len(filtered_points)}")

    except Exception as e:
        log(f"⚠️ 高度过滤失败: {str(e)}")
        return tower_obbs

    log_memory_usage("高度过滤后")

    # ==================== 改进的聚类处理 ====================
    chunk_size = 50000  # 增大分块尺寸
    chunks = [filtered_points[i:i + chunk_size] for i in range(0, len(filtered_points), chunk_size)]
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    log("\n=== 开始聚类处理 ===")
    log(f"分块数量: {len(chunks)}")
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
            log_memory_usage(f"分块{i + 1}处理后")

    # ==================== 杆塔检测与去重 ====================
    unique_labels = set(all_labels) - {-1}
    tower_obbs = []  # 存储最终杆塔信息
    tower_info_list = []  # 存储杆塔信息列表
    tower_centers = []  # 存储杆塔中心点用于去重

    log(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")
    progress(75)

    # 综合质量指标函数
    def calculate_quality(height, width, points_count):
        """计算综合质量指标：高度×宽度×点数对数"""
        return height * width * math.log(points_count + 1)

    for label_idx, label in enumerate(unique_labels):
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]
            points_count = len(cluster_points)

            # 跳过点数过少的簇
            if points_count < min_points:
                continue

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 尺寸过滤条件
            height = extents[2]
            width = max(extents[0], extents[1])
            aspect_ratio = height / width

            if not (height > min_height and min_width < width < max_width and aspect_ratio > aspect_ratio_threshold):
                continue

            # 计算正确全局坐标
            obb_center = obb.transform[:3, 3] + centroid

            # 增强去重检查
            is_duplicate = False
            is_strict_duplicate = False
            existing_index = -1

            for idx, existing_center in enumerate(tower_centers):
                distance = np.linalg.norm(obb_center - existing_center)

                # 1. 首先检查是否严格重复（距离<2米）
                if distance < strict_duplicate_threshold:
                    is_strict_duplicate = True
                    is_duplicate = True
                    existing_index = idx
                    break
                # 2. 检查是否距离过近（距离<duplicate_threshold）
                elif distance < duplicate_threshold:
                    is_duplicate = True
                    existing_index = idx
                    break

            if is_strict_duplicate:
                # 计算质量指标
                current_quality = calculate_quality(height, width, points_count)
                existing_quality = calculate_quality(
                    tower_info_list[existing_index]["height"],
                    tower_info_list[existing_index]["width"],
                    tower_info_list[existing_index]["点数"]
                )

                # 保留质量更好的检测结果
                if current_quality > existing_quality:
                    log(f"🔄 严格重复杆塔{label} (距离: {distance:.2f}m)，用当前杆塔替换原有杆塔 (质量 {current_quality:.1f} > {existing_quality:.1f})")

                    # 移除原有杆塔信息
                    del tower_obbs[existing_index]
                    del tower_centers[existing_index]
                    del tower_info_list[existing_index]

                    # 继续添加当前杆塔（后面会添加）
                else:
                    log(f"⚠️ 跳过严格重复杆塔{label} (距离: {distance:.2f}m)，保留质量更高的杆塔 (质量 {existing_quality:.1f} > {current_quality:.1f})")
                    continue
            elif is_duplicate:
                log(f"⚠️ 跳过重复杆塔{label} (距离: {distance:.1f}m)")
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

            # 计算质量指标
            quality = calculate_quality(height, width, points_count)

            # 保存杆塔信息
            tower_info = {
                "center": obb_center,
                "rotation": rotation_matrix,
                "extent": extents,
                "height": height,
                "width": width,
                "north_angle": north_angle,
                "points": cluster_points,
                "quality": quality
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
                "长宽比": aspect_ratio,
                "点数": points_count,
                "质量指标": quality
            })

            # 保存点云
            original_points = cluster_points + centroid
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(original_points, None, header_info, output_path, log)

            log(f"✅ 杆塔{label}: {height:.1f}m高 | {width:.1f}m宽 | 点数: {points_count} | 质量: {quality:.1f} | 中心坐标{obb_center}")

            progress(75 + int(15 * (label_idx + 1) / len(unique_labels)))

        except Exception as e:
            log(f"⚠️ 簇{label} 处理失败: {str(e)}")
            import traceback
            log(traceback.format_exc())
            continue
        finally:
            del cluster_points, cluster_pc, obb
            gc.collect()

    # ==================== 结果验证 ====================
    def verify_towers(tower_obbs, log):
        """验证杆塔结果合理性"""
        if not tower_obbs:
            return

        log("\n=== 杆塔结果验证 ===")

        # 1. 检查位置是否过于接近
        positions = np.array([t['center'] for t in tower_obbs])
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                dist = np.linalg.norm(positions[i] - positions[j])
                if dist < 5.0:  # 5米内视为可疑
                    log(f"⚠️ 警告: 杆塔{i}和杆塔{j}距离过近 ({dist:.2f}m)")

        # 2. 检查尺寸合理性
        for i, tower in enumerate(tower_obbs):
            h = tower['height']
            w = tower['width']
            ar = h / w
            if h < min_height or w < min_width or w > max_width or ar < aspect_ratio_threshold:
                log(f"⚠️ 警告: 杆塔{i}尺寸异常 高度={h:.1f}m, 宽度={w:.1f}m, 长宽比={ar:.1f}")

        # 3. 点数检查
        min_valid_points = min_points * 0.5  # 最小合理点数
        for i, tower in enumerate(tower_obbs):
            if 'points' in tower and len(tower['points']) < min_valid_points:
                log(f"⚠️ 警告: 杆塔{i}点数过少 ({len(tower['points'])} < {min_valid_points})")

        log("✅ 验证完成")

    # 执行验证
    verify_towers(tower_obbs, log)

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
    log_memory_usage("清理后")

    progress(100)
    log("✅ 杆塔提取完成")
    return tower_obbs


def _save_tower_las(points, colors, header_info, output_path, log_callback=None):
    """优化的LAS保存函数"""
    try:
        header = laspy.LasHeader(point_format=3, version=header_info["version"])
        header.scales = header_info["scales"]
        header.offsets = header_info["offsets"]

        las = laspy.LasData(header)
        las.x = points[:, 0].astype(np.float64)
        las.y = points[:, 1].astype(np.float64)
        las.z = points[:, 2].astype(np.float64)

        # 添加分类信息（如果支持）
        if "point_format" in header_info and header_info["point_format"].has_classification:
            las.classification = np.zeros(len(points), dtype=np.uint8)  # 默认为0

        las.write(output_path)
        if log_callback:
            log_callback(f"保存成功：{output_path}")
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 保存失败 {output_path}: {str(e)}")


def create_obb_geometries(tower_obbs):
    """将杆塔信息转换为Open3D OBB几何体列表"""
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


# 兼容性函数
def extract_towers_optimized(*args, **kwargs):
    return extract_towers(*args, **kwargs)


if __name__ == "__main__":
    """测试函数"""
    start_time = time.time()
    try:
        # 测试参数设置
        extract_towers(
            input_las_path="E:/pointcloudhookup002/output/point_2.las",
            eps=8.0,
            min_points=80,
            aspect_ratio_threshold=0.8,
            min_height=15.0,
            max_width=50.0,
            min_width=8,
            duplicate_threshold=30.0,
            strict_duplicate_threshold=2.0
        )
    except Exception as e:
        print(f"⚠️ 程序错误: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        print(f"\n总运行时间: {time.time() - start_time:.1f}秒")