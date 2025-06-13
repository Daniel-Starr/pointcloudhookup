import laspy
import numpy as np
import open3d as o3d
from sklearn.cluster import DBSCAN
import gc
import time


def extract_and_visualize_towers(input_las_path, output_las_dir="output_towers", eps=3.5, min_points=50,
                                 aspect_ratio_threshold=2.0, min_height=15.0, max_width=40.0, min_width=5):
    """提取杆塔并计算海拔高度"""
    output_dir = output_las_dir
    raw_points = None

    # 读取点云数据
    try:
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
    except Exception as e:
        print(f"⚠️ 文件读取失败: {str(e)}")
        return

    # 高度过滤
    try:
        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)
        filtered_points = points[z_values > (base_height + 3.0)]  # 基于海拔高度过滤
    except Exception as e:
        print(f"⚠️ 高度过滤失败: {str(e)}")
        return

    # DBSCAN聚类
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0
    chunk_size = 50000
    chunks = [filtered_points[i:i + chunk_size] for i in range(0, len(filtered_points), chunk_size)]

    print("\n=== 开始聚类处理 ===")
    for i, chunk in enumerate(chunks):
        try:
            clustering = DBSCAN(eps=eps, min_samples=min_points).fit(chunk)
            chunk_labels = clustering.labels_
            chunk_labels[chunk_labels != -1] += current_label
            all_labels[i * chunk_size:(i + 1) * chunk_size] = chunk_labels
            current_label = np.max(chunk_labels) + 1 if np.any(chunk_labels != -1) else current_label
        except Exception as e:
            print(f"⚠️ 聚类失败（块{i}）: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    obb_list = []
    unique_labels = set(all_labels) - {-1}
    tower_centers = []

    # 提取杆塔信息并计算海拔高度
    print(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")
    for label in unique_labels:
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            # 计算OBB
            obb = cluster_points  # 获取杆塔点集
            height = np.max(obb[:, 2]) - np.min(obb[:, 2])  # 高度计算

            # 计算海拔高度：使用点云底部的平均高度
            base_height = np.mean(obb[:, 2])

            # 计算中心坐标
            obb_center = np.mean(obb, axis=0)

            # 过滤不符合尺寸要求的杆塔
            if not (height > min_height and np.ptp(obb[:, 0]) < max_width and np.ptp(obb[:, 1]) < max_width):
                continue

            tower_centers.append(obb_center)

            # 保存点云
            output_path = f"{output_dir}/tower_{label}.las"
            _save_tower_las(obb + centroid, None, header_info, output_path)

            # 创建可视化的OBB（Oriented Bounding Box）
            obb_mesh = o3d.geometry.LineSet()
            obb_list.append(obb_mesh)

            # 输出杆塔信息
            print(f"✅ 杆塔{label}: {height:.1f}m高 | 中心坐标{obb_center} | 海拔高度: {base_height:.2f}")

        except Exception as e:
            print(f"⚠️ 处理杆塔{label}失败: {str(e)}")
            continue
        finally:
            del cluster_points
            gc.collect()

    # 可视化
    print("\n=== 可视化 ===")
    try:
        vis = o3d.visualization.Visualizer()
        vis.create_window()
        for obb in obb_list:
            vis.add_geometry(obb)
        vis.run()
        vis.destroy_window()
    except Exception as e:
        print(f"⚠️ 可视化失败: {str(e)}")

    print("\n=== 完成 ===")
    return tower_centers


def _save_tower_las(points, colors, header_info, output_path):
    """保存点云数据为LAS格式"""
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
        print(f"保存成功：{output_path}")
    except Exception as e:
        print(f"⚠️ 保存失败 {output_path}: {str(e)}")


# 调用函数
if __name__ == "__main__":
    input_las_path = "E:\pointcloudhookup\output\point_2.las"  # 输入点云路径
    output_las_dir = "output_towers"  # 输出目录
    towers = extract_and_visualize_towers(input_las_path, output_las_dir)
    print(f"提取的杆塔信息：{towers}")
