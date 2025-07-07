
import os
import numpy as np
import open3d as o3d
import laspy
import trimesh
from sklearn.cluster import DBSCAN
import gc

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # 地球半径，单位米
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    c = 2*np.arcsin(np.sqrt(a))
    return R * c

def extract_and_visualize_towers(las_path: str):
    if not os.path.exists(las_path):
        raise FileNotFoundError(f"未找到文件: {las_path}")

    with laspy.open(las_path) as lasf:
        las = lasf.read()
        points = np.vstack((las.x, las.y, las.z)).T.astype(np.float32)

    z_filter = np.percentile(points[:, 2], 25)
    filtered = points[points[:, 2] > z_filter + 3.0]

    db = DBSCAN(eps=3.5, min_samples=50, n_jobs=-1).fit(filtered)
    labels = db.labels_

    obb_results = []
    unique_labels = set(labels) - {-1}
    tower_centers = []
    output = []

    for label in unique_labels:
        cluster_pts = filtered[labels == label]
        if len(cluster_pts) < 50:
            continue

        pc = trimesh.PointCloud(cluster_pts)
        obb = pc.bounding_box_oriented
        extents = obb.extents
        height = extents[2]
        width = max(extents[0], extents[1])
        if not (height > 15 and 5 < width < 40 and height / width > 2):
            continue

        center = obb.transform[:3, 3]
        is_duplicate = any(np.linalg.norm(center - c) < 25 for c in tower_centers)
        if is_duplicate:
            continue
        tower_centers.append(center)

        # 海拔高度估计：取 cluster_pts 最底部 20% 的点平均 z 值
        z_sorted = cluster_pts[cluster_pts[:, 2].argsort()]
        base_z = np.mean(z_sorted[:max(3, len(z_sorted)//5), 2])

        # 使用 OBB 构建线框
        obb_o3d = o3d.geometry.OrientedBoundingBox()
        obb_o3d.center = center
        obb_o3d.extent = extents
        obb_o3d.R = obb.transform[:3, :3]
        lineset = o3d.geometry.LineSet.create_from_oriented_bounding_box(obb_o3d)
        lineset.paint_uniform_color([1.0, 0.0, 0.0])

        # 提取旋转角度：以 R 的方向推测偏角（例如绕 Z 轴的角度）
        R = obb_o3d.R
        forward = R[:, 0]  # 取第一列向量作为前向方向
        angle_rad = np.arctan2(forward[1], forward[0])
        angle_deg = np.degrees(angle_rad)

        output.append({
            'bbox': lineset,
            'lng': center[0],
            'lat': center[1],
            'alt': base_z,
            'r': round(angle_deg, 3)
        })

    return points, output

if __name__ == "__main__":
    extract_and_visualize_towers("E:\pointcloudhookup\output\point_2.las")