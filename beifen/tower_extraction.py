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


# 修复重复下采样问题 - tower_extraction.py

def extract_towers(
        input_las_path,
        progress_callback=None,
        log_callback=None,
        # 参数保持不变
        eps=8.0,
        min_points=80,
        aspect_ratio_threshold=0.8,
        min_height=15.0,
        max_width=50.0,
        min_width=8,
        duplicate_threshold=25.0,
        # 新增参数控制是否下采样
        skip_downsampling=True,  # 跳过下采样（主界面已下采样）
        max_points_for_processing=500000
):
    """
    修复重复下采样的杆塔提取算法
    - 如果主界面已经下采样，设置skip_downsampling=True
    - 如果直接测试原始文件，设置skip_downsampling=False
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

    # ==================== 智能数据读取 ====================
    try:
        log("📂 读取点云文件...")
        progress(5)

        with laspy.open(input_las_path) as las_file:
            header = las_file.header
            total_points = header.point_count

            # 检查文件路径，判断是否已经下采样
            is_downsampled_file = ("point_2.las" in input_las_path or
                                   "output" in input_las_path or
                                   skip_downsampling)

            if is_downsampled_file:
                log(f"🔍 检测到已下采样文件: {total_points:,} 个点")
                log("⚡ 跳过下采样步骤，直接使用现有数据")

                # 直接读取全部数据
                las = las_file.read()
                raw_points = np.stack([las.x, las.y, las.z], axis=1).astype(np.float32)

            else:
                log(f"📊 检测到原始文件: {total_points:,} 个点")

                # 只有原始文件才进行下采样
                if total_points > max_points_for_processing:
                    log(f"⚡ 执行下采样: {total_points:,} → {max_points_for_processing:,} 点")

                    las = las_file.read()
                    sample_ratio = max_points_for_processing / total_points
                    indices = np.random.choice(total_points, max_points_for_processing, replace=False)
                    raw_points = np.stack([las.x[indices], las.y[indices], las.z[indices]], axis=1).astype(np.float32)

                    log(f"✅ 下采样完成: {len(raw_points):,} 点")
                else:
                    las = las_file.read()
                    raw_points = np.stack([las.x, las.y, las.z], axis=1).astype(np.float32)
                    log(f"✅ 直接使用原始数据: {len(raw_points):,} 点")

            # 计算质心和相对坐标
            centroid = np.mean(raw_points, axis=0)
            points = raw_points - centroid

            header_info = {
                "scales": header.scales,
                "offsets": header.offsets,
                "point_format": header.point_format,
                "version": header.version,
                "centroid": centroid,
                "original_count": total_points,
                "processed_count": len(raw_points),
                "is_downsampled": is_downsampled_file
            }

            del las, raw_points
            gc.collect()

    except Exception as e:
        log(f"⚠️ 文件读取失败: {str(e)}")
        return tower_obbs

    # ==================== 高度过滤 ====================
    try:
        log("🔍 执行高度过滤...")
        progress(10)

        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)
        filtered_points = points[z_values > (base_height + 3.0)]

        filter_ratio = len(filtered_points) / len(points)
        log(f"✅ 高度过滤: {len(points):,} → {len(filtered_points):,} 点 (保留率: {filter_ratio:.1%})")

        if len(filtered_points) < 1000:
            log("⚠️ 过滤后点数太少，降低过滤阈值")
            filtered_points = points[z_values > (base_height + 1.0)]
            log(f"📈 调整后点数: {len(filtered_points):,}")

    except Exception as e:
        log(f"⚠️ 高度过滤失败: {str(e)}")
        return tower_obbs

    # ==================== 分块聚类处理 ====================
    chunk_size = 50000
    total_chunks = (len(filtered_points) + chunk_size - 1) // chunk_size

    log(f"\n=== 分块聚类信息 ===")
    log(f"📦 数据来源: {'已下采样文件' if header_info['is_downsampled'] else '原始文件'}")
    log(f"📊 处理点数: {len(filtered_points):,}")
    log(f"🔢 块大小: {chunk_size:,}")
    log(f"📋 分块数: {total_chunks}")

    chunks = [filtered_points[i:i + chunk_size] for i in range(0, len(filtered_points), chunk_size)]
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    progress(20)

    for i, chunk in enumerate(chunks):
        try:
            chunk_progress = 20 + int(50 * i / len(chunks))
            log(f"🔄 处理分块 {i + 1}/{len(chunks)} ({len(chunk):,}点)")

            clustering = DBSCAN(
                eps=eps,
                min_samples=min_points,
                n_jobs=-1,
                algorithm='ball_tree'
            ).fit(chunk)

            chunk_labels = clustering.labels_
            valid_labels = chunk_labels[chunk_labels != -1]

            if len(valid_labels) > 0:
                chunk_labels[chunk_labels != -1] += current_label
                all_labels[i * chunk_size:min((i + 1) * chunk_size, len(filtered_points))] = chunk_labels
                current_label = np.max(chunk_labels) + 1
                log(f"   ✅ 发现 {len(set(valid_labels))} 个聚类")
            else:
                all_labels[i * chunk_size:min((i + 1) * chunk_size, len(filtered_points))] = chunk_labels
                log(f"   ❌ 未发现有效聚类")

            progress(chunk_progress)

        except Exception as e:
            log(f"⚠️ 分块{i + 1}聚类失败: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    # ==================== 杆塔检测与去重 ====================
    unique_labels = set(all_labels) - {-1}
    tower_centers = []

    log(f"\n=== 杆塔检测 ===")
    log(f"🎯 候选聚类数量: {len(unique_labels)}")
    progress(75)

    valid_towers = 0
    for label_idx, label in enumerate(unique_labels):
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 几何过滤
            height = extents[2]
            width = max(extents[0], extents[1])
            aspect_ratio = height / width

            if not (height > min_height and min_width < width < max_width and aspect_ratio > aspect_ratio_threshold):
                continue

            # 计算全局坐标
            obb_center = obb.transform[:3, 3] + header_info["centroid"]

            # 去重检查
            is_duplicate = False
            for existing in tower_centers:
                distance = np.linalg.norm(obb_center - existing)
                if distance < duplicate_threshold:
                    is_duplicate = True
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
                "points": cluster_points,
                "label": label
            }
            tower_obbs.append(tower_info)
            tower_centers.append(obb_center)

            tower_info_list.append({
                "ID": f"tower_{label}",
                "经度": obb_center[0],
                "纬度": obb_center[1],
                "海拔高度": obb_center[2],
                "杆塔高度": height,
                "北方向偏角": north_angle,
                "宽度": width,
                "长宽比": aspect_ratio,
                "点数": len(cluster_points)
            })

            # 保存点云
            original_points = cluster_points + header_info["centroid"]
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(original_points, None, header_info, output_path, log)

            valid_towers += 1
            log(f"✅ 杆塔{valid_towers}: {height:.1f}m高×{width:.1f}m宽 (标签{label})")

            progress(75 + int(15 * (label_idx + 1) / len(unique_labels)))

        except Exception as e:
            log(f"⚠️ 簇{label} 处理失败: {str(e)}")
            continue
        finally:
            del cluster_points, cluster_pc, obb
            gc.collect()

    # ==================== 保存结果 ====================
    if tower_info_list:
        try:
            output_excel_path = "towers_info.xlsx"
            df = pd.DataFrame(tower_info_list)
            df.to_excel(output_excel_path, index=False)

            log(f"\n📊 检测完成统计:")
            log(f"   数据来源: {'已下采样' if header_info['is_downsampled'] else '原始文件'}")
            log(f"   处理点数: {header_info['processed_count']:,}")
            log(f"   过滤点数: {len(filtered_points):,}")
            log(f"   分块数量: {total_chunks}")
            log(f"   有效杆塔: {len(tower_obbs)}")
            log(f"✅ 结果已保存: {output_excel_path}")

        except Exception as e:
            log(f"⚠️ 保存Excel失败: {str(e)}")
    else:
        log("\n⚠️ 未检测到任何杆塔")

    progress(100)
    log("✅ 杆塔提取完成")
    return tower_obbs


# 其他函数保持不变
def _save_tower_las(points, colors, header_info, output_path, log_callback=None):
    """保存LAS文件"""
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
            log_callback(f"💾 保存: {output_path.name}")
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 保存失败: {str(e)}")


def create_obb_geometries(tower_obbs):
    """创建几何体"""
    geometries = []
    for tower in tower_obbs:
        try:
            obb_o3d = o3d.geometry.OrientedBoundingBox()
            obb_o3d.center = tower['center']
            obb_o3d.extent = tower['extent']
            obb_o3d.R = tower['rotation']
            obb_mesh = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb_o3d)
            obb_mesh.paint_uniform_color([1, 0, 0])
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