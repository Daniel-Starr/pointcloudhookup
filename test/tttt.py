import gc

import pandas as pd


def extract_towers(
        input_las_path,
        progress_callback=None,
        log_callback=None,
        eps=10.0,
        min_points=100,
        aspect_ratio_threshold=0.8,
        min_height=15.0,
        max_width=50.0,
        min_width=8,
        merge_threshold=6.0,
        duplicate_threshold=10.0
):
    tower_obbs = []
    tower_info_list = []

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    def progress(value):
        if progress_callback: progress_callback(value)

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
    except Exception as e:
        log(f"⚠️ 文件读取失败: {str(e)}")
        return tower_obbs

    # ==================== 高度过滤优化 ====================
    try:
        progress(10)
        z_values = points[:, 2]
        base_height = np.percentile(z_values, 25)
        filtered_points = points[z_values > (base_height + 3.0)]
    except Exception as e:
        log(f"⚠️ 高度过滤失败: {str(e)}")
        return tower_obbs

    # ==================== 改进的聚类处理 ====================
    chunk_size = 50000
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
                algorithm='ball_tree'
            ).fit(chunk)
            chunk_labels = clustering.labels_
            chunk_labels[chunk_labels != -1] += current_label
            all_labels[i * chunk_size:(i + 1) * chunk_size] = chunk_labels
            current_label = np.max(chunk_labels) + 1 if np.any(chunk_labels != -1) else current_label
            progress(20 + int(30 * (i + 1) / len(chunks)))
        except Exception as e:
            log(f"⚠️ 分块聚类失败（块{i}）: {str(e)}")
        finally:
            del chunk, clustering, chunk_labels
            gc.collect()

    # ==================== 聚类后处理：合并相邻簇 ====================
    log("\n=== 合并相邻簇 ===")
    progress(50)

    # 获取所有非噪声簇的标签
    unique_labels = set(all_labels) - {-1}
    if not unique_labels:
        log("⚠️ 没有有效簇可合并")
        merged_labels = all_labels
        unique_labels = set()
    else:
        # 计算每个簇的中心点
        cluster_centers = []
        label_to_index = {}
        valid_labels = []

        for label in unique_labels:
            cluster_mask = (all_labels == label)
            cluster_points = filtered_points[cluster_mask]
            if len(cluster_points) > 0:
                cluster_centers.append(np.mean(cluster_points, axis=0))
                label_to_index[label] = len(cluster_centers) - 1
                valid_labels.append(label)

        if not cluster_centers:
            log("⚠️ 没有有效簇可合并")
            merged_labels = all_labels
        else:
            cluster_centers = np.array(cluster_centers)

            # 构建簇中心的KDTree
            tree = KDTree(cluster_centers)

            # 查找邻近簇
            neighbors = tree.query_radius(cluster_centers, r=merge_threshold)

            # 使用并查集合并簇
            parent = list(range(len(cluster_centers)))

            def find(x):
                if parent[x] != x:
                    parent[x] = find(parent[x])
                return parent[x]

            def union(x, y):
                root_x = find(x)
                root_y = find(y)
                if root_x != root_y:
                    # 按簇大小合并
                    size_x = np.sum(all_labels == valid_labels[x])
                    size_y = np.sum(all_labels == valid_labels[y])
                    if size_x > size_y:
                        parent[root_y] = root_x
                    else:
                        parent[root_x] = root_y

            # 合并邻近簇
            for i, neighbor_indices in enumerate(neighbors):
                for j in neighbor_indices:
                    if i < j:  # 避免重复合并
                        union(i, j)

            # 创建新标签映射
            new_labels = {}
            current_max_label = max(unique_labels) + 1

            for i in range(len(cluster_centers)):
                root = find(i)
                if root not in new_labels:
                    new_labels[root] = current_max_label
                    current_max_label += 1

            # 更新标签
            merged_labels = all_labels.copy()
            for label in valid_labels:
                idx = label_to_index[label]
                new_label = new_labels[find(idx)]
                merged_labels[all_labels == label] = new_label

    # 更新唯一标签
    unique_labels = set(merged_labels) - {-1}
    log(f"✅ 合并后簇数量: {len(unique_labels)}")
    progress(55)

    # ==================== 杆塔检测与去重 ====================
    log(f"\n=== 开始杆塔检测（候选簇：{len(unique_labels)}个） ===")
    progress(60)

    for label_idx, label in enumerate(unique_labels):
        cluster_points = None
        cluster_pc = None
        obb = None

        try:
            cluster_mask = (merged_labels == label)
            cluster_points = filtered_points[cluster_mask]

            if len(cluster_points) < min_points:
                log(f"⚠️ 簇 {label} 点数不足: {len(cluster_points)} < {min_points}")
                continue

            # 计算OBB
            cluster_pc = trimesh.PointCloud(cluster_points)
            obb = cluster_pc.bounding_box_oriented
            extents = obb.extents

            # 改进的尺寸合理性检查
            height = extents[2]
            width = max(extents[0], extents[1])

            # 1. 检查高度和宽度的比例关系
            if height / width < 1.0:  # 杆塔高度应大于宽度
                log(f"⚠️ 跳过簇 {label} (高度 {height:.1f}m < 宽度 {width:.1f}m)")
                continue

            # 2. 检查绝对尺寸范围
            if not (min_height < height < 100.0):
                log(f"⚠️ 跳过簇 {label} (高度异常: {height:.1f}m)")
                continue

            if not (min_width < width < max_width):
                log(f"⚠️ 跳过簇 {label} (宽度异常: {width:.1f}m)")
                continue

            # 3. 检查高宽比
            aspect_ratio = height / width
            if aspect_ratio < aspect_ratio_threshold:
                log(f"⚠️ 跳过簇 {label} (高宽比过低: {aspect_ratio:.1f} < {aspect_ratio_threshold})")
                continue

            # 计算正确全局坐标
            obb_center = obb.transform[:3, 3] + centroid

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

            # 增强去重检查
            is_duplicate = False
            for existing in tower_obbs:
                # 1. 检查中心点距离
                center_dist = np.linalg.norm(obb_center - existing["center"])
                if center_dist < duplicate_threshold:
                    is_duplicate = True
                    break

                # 2. 检查OBB重叠
                try:
                    # 创建两个OBB
                    obb1 = trimesh.primitives.Box(
                        extents=extents,
                        transform=obb.transform
                    )
                    obb2 = trimesh.primitives.Box(
                        extents=existing["extent"],
                        transform=np.eye(4)
                    )
                    obb2.apply_translation(existing["center"] - centroid)

                    # 计算OBB重叠体积
                    intersection = obb1.intersection(obb2)
                    if intersection.volume > 0.1 * min(obb1.volume, obb2.volume):
                        is_duplicate = True
                        break
                except Exception as e:
                    log(f"⚠️ OBB重叠检测失败: {str(e)}")

            if is_duplicate:
                log(f"⚠️ 跳过重复杆塔（标签: {label}, 中心: {obb_center})")
                continue

            # 保存杆塔信息
            tower_info = {
                "center": obb_center,
                "rotation": obb.transform[:3, :3],
                "extent": extents,
                "height": height,
                "width": width,
                "north_angle": north_angle
            }
            tower_obbs.append(tower_info)
            tower_info_list.append({
                "ID": label,
                "经度": obb_center[0],
                "纬度": obb_center[1],
                "海拔高度": obb_center[2],
                "杆塔高度": height,
                "北方向偏角": north_angle
            })

            # 保存点云
            original_points = cluster_points + centroid
            output_path = output_dir / f"tower_{label}.las"
            _save_tower_las(original_points, None, header_info, output_path, log)

            log(f"✅ 检测到杆塔 {label}: {height:.1f}m高, {width:.1f}m宽")
            progress(60 + int(30 * (label_idx + 1) / len(unique_labels)))

        except Exception as e:
            log(f"⚠️ 处理簇 {label} 失败: {str(e)}")
            continue
        finally:
            # 安全清理资源
            if cluster_points is not None:
                del cluster_points
            if cluster_pc is not None:
                del cluster_pc
            if obb is not None:
                del obb
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

    progress(95)
    log("✅ 杆塔提取完成")
    return tower_obbs