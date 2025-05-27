import laspy
import numpy as np
import trimesh
import open3d as o3d
from sklearn.cluster import DBSCAN
from pathlib import Path
import warnings
import gc
import time
import os

# 配置环境
os.environ["OPEN3D_CPU_RENDERING"] = "false"
warnings.filterwarnings("ignore", category=UserWarning, module="trimesh")


def extract_visualize_save_towers(
        input_las_path,
        output_las_dir="output_towers",
        eps=3.5,  # 增大邻域半径
        min_points=50,  # 适当增加最小点数
        aspect_ratio_threshold=2.0,  # 降低高宽比要求
        min_height=15.0,
        max_width=40.0,  # 增大最大宽度
        min_width=5, #

):
    """大尺寸杆塔优化检测函数"""
    output_dir = Path(output_las_dir)
    output_dir.mkdir(exist_ok=True)

    # ==================== 数据读取和预处理 ====================
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

    # ==================== 高度过滤优化 ====================
    try:
        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)  # 降低基准高度
        filtered_points = points[z_values > (base_height + 3.0)]  # 提高过滤阈值
    except Exception as e:
        print(f"⚠️ 高度过滤失败: {str(e)}")
        return

    # ==================== 可视化初始化 ====================
    vis_pcd = o3d.geometry.PointCloud()
    vis_pcd.points = o3d.utility.Vector3dVector(raw_points)
    vis_pcd.paint_uniform_color([0.2, 0.5, 0.8])

    # ==================== 改进的聚类处理 ====================
    chunk_size = 50000  # 增大分块尺寸
    chunks = [filtered_points[i:i + chunk_size] for i in range(0, len(filtered_points), chunk_size)]
    all_labels = np.full(len(filtered_points), -1, dtype=np.int32)
    current_label = 0

    print("\n=== 开始聚类处理 ===")
    for i, chunk in enumerate(chunks):
        try:
            print(f"处理分块 {i + 1}/{len(chunks)} ({len(chunk)}点)")
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
        except Exception as e:
            print(f"⚠️ 分块聚类失败（块{i}）: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    # ==================== 杆塔检测与去重 ====================

    obb_list = []
    unique_labels = set(all_labels) - {-1}
    tower_centers = []
    duplicate_threshold = 25.0  # 修改为固定5米阈值

    print(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")

    for label in unique_labels:
        try:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 尺寸过滤条件
            height = extents[2]
            width = max(extents[0], extents[1])
            if not (height > min_height and min_width < width < max_width and (height / width) > aspect_ratio_threshold):
                continue

            # 计算正确全局坐标
            obb_center = obb.transform[:3, 3] + centroid

            # 去重检查（5米内视为重复）
            is_duplicate = False
            for existing in tower_centers:
                if np.linalg.norm(obb_center - existing) < duplicate_threshold:  # 使用新阈值
                    is_duplicate = True
                    break
            if is_duplicate:
                print(f"⚠️ 跳过重复杆塔{label} (中心距: {np.linalg.norm(obb_center - existing):.1f}m)")
                continue

            # 保存杆塔信息
            tower_centers.append(obb_center)

            # 保存点云
            original_points = cluster_points + centroid
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(original_points, None, header_info, output_path)

            # 创建可视化OBB
            obb_o3d = o3d.geometry.OrientedBoundingBox()
            obb_o3d.center = obb_center
            obb_o3d.extent = extents
            obb_o3d.R = obb.transform[:3, :3]
            obb_mesh = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb_o3d)
            obb_mesh.paint_uniform_color([1, 0, 0])
            obb_list.append(obb_mesh)

            print(f"✅ 杆塔{label}: {height:.1f}m高 | {width:.1f}m宽 | 中心坐标{obb_center}")

        except Exception as e:
            print(f"⚠️ 簇{label} 处理失败: {str(e)}")
            continue
        finally:
            del cluster_points, cluster_pc, obb
            gc.collect()

    # ==================== 可视化系统 ====================
    print("\n=== 初始化可视化 ===")
    try:
        vis = o3d.visualization.Visualizer()
        vis.create_window(
            width=1600,
            height=1200,
            window_name=f"电力杆塔检测 - 发现{len(obb_list)}个杆塔",
            visible=True
        )

        # 添加元素
        vis.add_geometry(vis_pcd)
        for obb in obb_list:
            vis.add_geometry(obb)

        # 坐标系设置
        coord_size = max(15.0, np.ptp(raw_points, axis=0).max() / 10)
        coordinate = o3d.geometry.TriangleMesh.create_coordinate_frame(
            size=coord_size,
            origin=vis_pcd.get_center()
        )
        vis.add_geometry(coordinate)

        # 渲染设置
        render_opt = vis.get_render_option()
        render_opt.point_size = 1.5  # 缩小点尺寸
        render_opt.background_color = [0.95, 0.95, 0.95]
        render_opt.light_on = True

        # 视角控制
        ctr = vis.get_view_control()
        ctr.set_front([-0.5, -0.3, 0.8])
        ctr.set_lookat(vis_pcd.get_center())
        ctr.set_up([0, 0, 1])
        ctr.set_zoom(0.6)

        vis.run()
        vis.destroy_window()
    except Exception as e:
        print(f"⚠️ 可视化错误: {str(e)}")
    finally:
        del vis

    # ==================== 内存清理 ====================
    print("\n=== 清理内存 ===")
    del points, filtered_points, vis_pcd
    gc.collect()


def _save_tower_las(points, colors, header_info, output_path):
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
        print(f"保存成功：{output_path}")
    except Exception as e:
        print(f"⚠️ 保存失败 {output_path}: {str(e)}")


if __name__ == "__main__":
    start_time = time.time()
    try:
        extract_visualize_save_towers(
            input_las_path="output/point_2.las",
            output_las_dir="output_towers",
            eps=8.0,  # 根据场景调整
            min_points=80,  # 适用于密集点云
            aspect_ratio_threshold=0.8,
            min_height=15.0,
            max_width=50.0,
            min_width=8
        )
    except Exception as e:
        print(f"⚠️ 程序崩溃: {str(e)}")
    finally:
        print(f"\n总运行时间: {time.time() - start_time:.1f}秒")