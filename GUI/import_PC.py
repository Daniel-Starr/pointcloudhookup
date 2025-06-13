import os
import gc
import laspy
import numpy as np
import open3d as o3d
from typing import Callable

def process_chunk(points_chunk, voxel_size):
    """处理单个点云块，执行体素下采样"""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points_chunk.astype(np.float64))
    downpcd = pcd.voxel_down_sample(voxel_size)
    return np.asarray(downpcd.points)

def run_voxel_downsampling(
    input_path: str,
    output_path: str,
    voxel_size: float = 0.1,
    chunk_size: int = 1000000,
    progress_callback: Callable[[int], None] = None,
    log_callback: Callable[[str], None] = None
):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在: {os.path.abspath(input_path)}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    las = laspy.read(input_path)
    total_points = len(las.points)

    if log_callback:
        log_callback(f"📂 原始点数: {total_points}")
        log_callback(f"✨ 开始下采样（voxel_size={voxel_size}, chunk_size={chunk_size}）")

    header = laspy.LasHeader(
        point_format=las.header.point_format,
        version=las.header.version
    )
    header.offsets = las.header.offsets
    header.scales = las.header.scales

    downsampled = laspy.LasData(header)
    output_points = []

    for i, start in enumerate(range(0, total_points, chunk_size)):
        end = min(start + chunk_size, total_points)
        chunk = las.points[start:end]
        points = np.vstack((chunk.x, chunk.y, chunk.z)).T
        down_points = process_chunk(points, voxel_size)
        output_points.append(down_points)

        del chunk, points, down_points
        gc.collect()

        if log_callback:
            log_callback(f"✅ 已完成第{i+1}块：{end - start} 点")
        if progress_callback:
            progress_callback(int((end / total_points) * 100))

    final_points = np.vstack(output_points)
    downsampled.x = final_points[:, 0]
    downsampled.y = final_points[:, 1]
    downsampled.z = final_points[:, 2]

    downsampled.write(output_path)

    if log_callback:
        log_callback(f"✅ 下采样完成，输出点数: {len(final_points)}")
        log_callback(f"📁 保存至：{output_path}")
