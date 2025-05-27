import laspy
import open3d as o3d
import numpy as np
import os
from tqdm import tqdm
import tempfile
import gc


def process_chunk(points_chunk, voxel_size):
    """使用 Open3D 对单个点云块进行体素下采样"""
    if len(points_chunk) == 0:
        return np.empty((0, 3))

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points_chunk.astype(np.float64))
    pcd_down = pcd.voxel_down_sample(voxel_size)
    return np.asarray(pcd_down.points)


def voxel_downsample_open3d(input_path, output_path, voxel_size=0.1, chunk_size=1000000):
    try:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {os.path.abspath(input_path)}")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_path = os.path.join(os.getcwd(), output_path)

        print("正在读取输入文件...")
        las = laspy.read(input_path)
        total_points = len(las.points)
        header = las.header

        print(f"原始点数: {total_points}")
        print(f"体素大小: {voxel_size}, 每块处理点数: {chunk_size}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_files = []

            print("开始分块处理...")
            with tqdm(total=total_points, desc="处理进度") as pbar:
                for start in range(0, total_points, chunk_size):
                    end = min(start + chunk_size, total_points)
                    chunk = las.points[start:end]

                    # 注意缩放与偏移（LAS 格式原始单位可能为整数）
                    x = chunk.x * header.scales[0] + header.offsets[0]
                    y = chunk.y * header.scales[1] + header.offsets[1]
                    z = chunk.z * header.scales[2] + header.offsets[2]
                    points = np.vstack((x, y, z)).T

                    down_points = process_chunk(points, voxel_size)
                    if len(down_points) > 0:
                        tmp_path = f"{tmpdir}/chunk_{start}.npy"
                        np.save(tmp_path, down_points)
                        tmp_files.append(tmp_path)

                    del chunk, points, down_points
                    gc.collect()
                    pbar.update(end - start)

            print("合并处理结果...")
            final_points = np.vstack([np.load(f) for f in tmp_files])

        print(f"下采样后点数: {len(final_points)}")

        print("构建输出点云...")
        # 创建新的 LasData 实例
        new_header = laspy.LasHeader(point_format=header.point_format, version=header.version)
        new_header.scales = header.scales
        new_header.offsets = header.offsets

        las_out = laspy.LasData(new_header)

        # 转换为整数编码存储（根据 scale 和 offset）
        las_out.x = ((final_points[:, 0] - new_header.offsets[0]) / new_header.scales[0]).astype(np.int32)
        las_out.y = ((final_points[:, 1] - new_header.offsets[1]) / new_header.scales[1]).astype(np.int32)
        las_out.z = ((final_points[:, 2] - new_header.offsets[2]) / new_header.scales[2]).astype(np.int32)

        print("写入输出文件...")
        las_out.write(output_path)

        print(f"✅ 成功生成下采样文件: {os.path.abspath(output_path)}")
        print(f"📉 原始点数: {total_points} → 下采样后点数: {len(final_points)}")

    except Exception as e:
        print(f"\n❌ 处理过程中发生错误: {str(e)}")


if __name__ == "__main__":
    # 示例参数（你可以替换为命令行参数解析器）
    input_file = "../pointcloud.las"
    output_file = "output_downsampled.las"
    voxel_size = 0.1
    chunk_size = 500000

    voxel_downsample_open3d(input_file, output_file, voxel_size, chunk_size)
