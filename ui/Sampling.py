
import laspy
import open3d as o3d
import numpy as np
import os
from tqdm import tqdm
import gc  # 添加垃圾回收模块


def process_chunk(points_chunk, las, voxel_size):
    """处理数据分块并返回下采样结果"""
    # 创建open3d点云
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points_chunk.astype(np.float64))

    # 执行体素下采样
    downpcd = pcd.voxel_down_sample(voxel_size)
    return np.asarray(downpcd.points)


def voxel_downsample_open3d(input_path, output_path, voxel_size, chunk_size=1000000):
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 读取输入文件
        print("正在读取输入文件...")
        las = laspy.read(input_path)
        total_points = len(las.points)

        # 创建输出文件头
        header = laspy.LasHeader(
            point_format=las.header.point_format,
            version=las.header.version
        )
        header.offsets = las.header.offsets
        header.scales = las.header.scales

        # 初始化输出点云
        downsampled = laspy.LasData(header)
        output_points = []

        # 分块处理数据
        print(f"开始分块处理（每块 {chunk_size} 个点）...")
        with tqdm(total=total_points, desc="处理进度") as pbar:
            for start in range(0, total_points, chunk_size):
                end = min(start + chunk_size, total_points)

                # 分块读取点数据
                chunk = las.points[start:end]
                points = np.vstack((chunk.x, chunk.y, chunk.z)).T

                # 处理当前分块
                down_points = process_chunk(points, las, voxel_size)
                output_points.append(down_points)

                # 释放内存
                del chunk, points, down_points
                gc.collect()
                pbar.update(end - start)

        # 合并所有结果
        print("合并处理结果...")
        final_points = np.vstack(output_points)

        # 构建最终点云
        downsampled = laspy.LasData(header)
        downsampled.x = final_points[:, 0]
        downsampled.y = final_points[:, 1]
        downsampled.z = final_points[:, 2]

        # 写入输出文件
        print("正在写入输出文件...")
        downsampled.write(output_path)

        print(f"\n成功生成下采样文件: {output_path}")
        print(f"原始点数: {total_points} → 下采样后点数: {len(final_points)}")

    except Exception as e:
        print(f"\n处理过程中发生错误: {str(e)}")


if __name__ == "__main__":
    input_file = "G:\Project\pointcloudhookup\pointcloud.las"
    output_file = "G:\Project\pointcloudhookup\output\point_2.las"
    voxel_size = 0.1  # 体素尺寸（根据内存调整）

    # 根据内存调整分块大小（建议：4GB内存用500000，8GB用1000000，16GB用2000000）
    chunk_size = 500000

    voxel_downsample_open3d(input_file, output_file, voxel_size, chunk_size)