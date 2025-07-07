#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立运行的轻量级杆塔提取工具
作者: AI Assistant
日期: 2025年
用途: 从点云数据中提取杆塔信息，节约系统资源

使用方法:
1. 直接运行: python standalone_tower_extraction.py
2. 命令行: python standalone_tower_extraction.py input.las
3. 导入使用: from standalone_tower_extraction import extract_towers
"""

import sys
import os
import argparse
from pathlib import Path
import time
import gc
import warnings

warnings.filterwarnings('ignore')


# 检查和导入依赖
def check_dependencies():
    """检查必要的依赖库"""
    missing_deps = []

    try:
        import numpy as np
    except ImportError:
        missing_deps.append('numpy')

    try:
        import pandas as pd
    except ImportError:
        missing_deps.append('pandas')

    try:
        import laspy
    except ImportError:
        missing_deps.append('laspy')

    try:
        from sklearn.cluster import DBSCAN
    except ImportError:
        missing_deps.append('scikit-learn')

    try:
        import trimesh
    except ImportError:
        missing_deps.append('trimesh')

    try:
        import psutil
    except ImportError:
        missing_deps.append('psutil')

    if missing_deps:
        print("❌ 缺少以下依赖库:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print("\n📦 请运行以下命令安装:")
        print(f"pip install {' '.join(missing_deps)}")
        return False

    print("✅ 所有依赖库检查通过")
    return True


# 只有通过检查才导入
if not check_dependencies():
    sys.exit(1)

import numpy as np
import pandas as pd
import laspy
from sklearn.cluster import DBSCAN
import trimesh
import psutil
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple, Optional, Callable

# 尝试导入可选依赖
try:
    import hdbscan

    HAS_HDBSCAN = True
    print("✅ HDBSCAN高性能聚类已启用")
except ImportError:
    HAS_HDBSCAN = False
    print("ℹ️ 使用标准DBSCAN聚类")

try:
    import open3d as o3d

    HAS_OPEN3D = True
    print("✅ Open3D可视化支持已启用")
except ImportError:
    HAS_OPEN3D = False
    print("ℹ️ 无Open3D支持，跳过可视化功能")


class StandaloneTowerExtractor:
    """独立的杆塔提取器"""

    def __init__(self, max_memory_percent: int = 30, max_threads: int = 6):
        self.max_memory_percent = max_memory_percent
        self.max_threads = max_threads
        self.total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        self.memory_limit_gb = self.total_memory_gb * max_memory_percent / 100

        print(f"🎯 独立杆塔提取器初始化:")
        print(f"   系统内存: {self.total_memory_gb:.1f}GB")
        print(f"   使用限制: {self.memory_limit_gb:.1f}GB ({max_memory_percent}%)")
        print(f"   线程限制: {max_threads}")

    def log_progress(self, message: str, step: int = None, total: int = None):
        """日志输出"""
        if step and total:
            percentage = int(step * 100 / total)
            print(f"[{percentage:3d}%] {message}")
        else:
            print(f"ℹ️ {message}")

    def monitor_memory(self, operation: str = ""):
        """监控内存使用"""
        memory_info = psutil.virtual_memory()
        used_gb = (memory_info.total - memory_info.available) / (1024 ** 3)
        percent = memory_info.percent

        print(f"💾 {operation} 内存使用: {used_gb:.1f}GB ({percent:.1f}%)")

        if percent > 80:
            print("⚠️ 内存使用率过高，建议关闭其他程序")

        return percent

    def read_las_file(self, file_path: str) -> Tuple[np.ndarray, Dict]:
        """读取LAS文件"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        self.log_progress(f"读取文件: {file_path}")
        self.log_progress(f"文件大小: {file_size_mb:.1f}MB")

        try:
            with laspy.open(file_path) as las_file:
                header_info = {
                    "scales": las_file.header.scales,
                    "offsets": las_file.header.offsets,
                    "point_format": las_file.header.point_format,
                    "version": las_file.header.version,
                    "point_count": las_file.header.point_count
                }

                # 根据文件大小决定读取策略
                if file_size_mb > 500:  # 大于500MB的文件分块读取
                    points = self._read_large_file(las_file)
                else:
                    las_data = las_file.read()
                    points = np.stack([las_data.x, las_data.y, las_data.z], axis=1).astype(np.float32)
                    del las_data

                # 计算并应用中心化
                centroid = np.mean(points, axis=0)
                points_centered = points - centroid
                header_info["centroid"] = centroid

                self.log_progress(f"读取完成: {len(points_centered):,} 个点")
                self.monitor_memory("文件读取后")

                return points_centered, header_info

        except Exception as e:
            raise Exception(f"读取LAS文件失败: {str(e)}")

    def _read_large_file(self, las_file) -> np.ndarray:
        """分块读取大文件"""
        self.log_progress("检测到大文件，使用分块读取...")

        chunk_size = 500_000  # 每次读取50万点
        points_list = []
        total_points = 0

        for i, chunk in enumerate(las_file.chunk_iterator(chunk_size)):
            chunk_points = np.stack([chunk.x, chunk.y, chunk.z], axis=1).astype(np.float32)
            points_list.append(chunk_points)
            total_points += len(chunk_points)

            self.log_progress(f"读取块 {i + 1}: {total_points:,} 点", i + 1, 10)

            # 内存检查
            if self.monitor_memory(f"块{i + 1}读取后") > 75:
                self.log_progress("内存使用率过高，停止读取更多数据")
                break

            # 限制最大块数
            if i >= 20:  # 最多20块
                self.log_progress("达到最大处理块数，停止读取")
                break

        combined_points = np.vstack(points_list)
        del points_list
        gc.collect()

        return combined_points

    def height_filter(self, points: np.ndarray) -> np.ndarray:
        """高度过滤"""
        self.log_progress("执行高度过滤...")

        z_values = points[:, 2]
        base_height = np.percentile(z_values, 20)  # 使用20百分位作为地面高度
        height_threshold = 2.5  # 高度阈值

        mask = z_values > (base_height + height_threshold)
        filtered_points = points[mask]

        self.log_progress(f"高度过滤完成: {len(points):,} -> {len(filtered_points):,} 点")
        return filtered_points

    def adaptive_downsample(self, points: np.ndarray) -> np.ndarray:
        """自适应降采样"""
        if len(points) <= 1_000_000:  # 小于100万点不降采样
            return points

        # 计算目标点数（基于内存限制）
        max_points = int(self.memory_limit_gb * 1024 ** 3 / 24)  # 每点约24字节
        max_points = min(max_points, 2_000_000)  # 最多200万点

        if len(points) > max_points:
            ratio = max_points / len(points)
            indices = np.random.choice(len(points), max_points, replace=False)
            sampled_points = points[indices]

            self.log_progress(f"自适应降采样: {len(points):,} -> {len(sampled_points):,} 点 (比例: {ratio:.1%})")
            return sampled_points

        return points

    def cluster_points(self, points: np.ndarray, eps: float = 10.0, min_samples: int = 50) -> np.ndarray:
        """点云聚类"""
        self.log_progress(f"开始聚类分析 (eps={eps}, min_samples={min_samples})...")
        self.monitor_memory("聚类前")

        # 选择聚类算法
        if HAS_HDBSCAN and len(points) < 800_000:
            # 小数据集使用HDBSCAN
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=min_samples,
                algorithm='boruvka_kdtree',
                n_jobs=self.max_threads
            )
            self.log_progress("使用HDBSCAN聚类算法")
        else:
            # 大数据集使用DBSCAN
            clusterer = DBSCAN(
                eps=eps,
                min_samples=min_samples,
                algorithm='kd_tree',
                n_jobs=self.max_threads
            )
            self.log_progress("使用DBSCAN聚类算法")

        # 执行聚类
        labels = clusterer.fit_predict(points)

        # 统计结果
        unique_labels = set(labels)
        n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        n_noise = list(labels).count(-1)

        self.log_progress(f"聚类完成: {n_clusters} 个簇, {n_noise} 个噪声点")
        self.monitor_memory("聚类后")

        return labels

    def detect_towers(self, points: np.ndarray, labels: np.ndarray,
                      min_height: float = 12.0, max_width: float = 60.0,
                      min_width: float = 6.0, aspect_ratio_threshold: float = 0.6) -> List[Dict]:
        """检测杆塔"""
        self.log_progress("开始杆塔检测...")

        unique_labels = set(labels) - {-1}
        towers = []

        for i, label in enumerate(unique_labels):
            if i % 100 == 0:  # 每100个簇显示进度
                self.log_progress(f"检测进度: {i}/{len(unique_labels)}", i, len(unique_labels))

            try:
                mask = labels == label
                cluster_points = points[mask]

                if len(cluster_points) < 30:  # 点数太少
                    continue

                # 计算边界框
                min_coords = np.min(cluster_points, axis=0)
                max_coords = np.max(cluster_points, axis=0)
                extents = max_coords - min_coords

                height = extents[2]
                width = max(extents[0], extents[1])

                if width <= 0:
                    continue

                aspect_ratio = height / width

                # 杆塔判断条件
                if (height > min_height and
                        min_width < width < max_width and
                        aspect_ratio > aspect_ratio_threshold):
                    center = (min_coords + max_coords) / 2

                    tower = {
                        "id": len(towers) + 1,
                        "center": center,
                        "height": height,
                        "width": width,
                        "aspect_ratio": aspect_ratio,
                        "point_count": len(cluster_points),
                        "extents": extents
                    }

                    towers.append(tower)

            except Exception:
                continue

        self.log_progress(f"杆塔检测完成: 发现 {len(towers)} 个候选杆塔")
        return towers

    def remove_duplicates(self, towers: List[Dict], distance_threshold: float = 25.0) -> List[Dict]:
        """去除重复检测"""
        if len(towers) <= 1:
            return towers

        self.log_progress("去除重复检测...")

        # 简单的距离去重
        unique_towers = []

        for tower in towers:
            is_duplicate = False

            for existing in unique_towers:
                distance = np.linalg.norm(tower['center'] - existing['center'])
                if distance < distance_threshold:
                    # 保留点数更多的塔
                    if tower['point_count'] <= existing['point_count']:
                        is_duplicate = True
                        break
                    else:
                        unique_towers.remove(existing)
                        break

            if not is_duplicate:
                unique_towers.append(tower)

        removed_count = len(towers) - len(unique_towers)
        if removed_count > 0:
            self.log_progress(f"去重完成: 移除 {removed_count} 个重复检测")

        return unique_towers

    def save_results(self, towers: List[Dict], header_info: Dict, output_dir: str = "output") -> str:
        """保存结果"""
        if not towers:
            self.log_progress("无杆塔数据，跳过保存")
            return None

        # 创建输出目录
        Path(output_dir).mkdir(exist_ok=True)

        # 恢复原始坐标系
        centroid = header_info["centroid"]
        for tower in towers:
            tower["center"] += centroid

        # 准备Excel数据
        excel_data = []
        for tower in towers:
            excel_data.append({
                "杆塔ID": f"T{tower['id']:03d}",
                "X坐标": tower["center"][0],
                "Y坐标": tower["center"][1],
                "Z坐标": tower["center"][2],
                "杆塔高度": tower["height"],
                "杆塔宽度": tower["width"],
                "长宽比": tower["aspect_ratio"],
                "点数": tower["point_count"]
            })

        # 保存Excel文件
        df = pd.DataFrame(excel_data)
        excel_path = os.path.join(output_dir, "杆塔检测结果.xlsx")
        df.to_excel(excel_path, index=False, engine='openpyxl')

        self.log_progress(f"结果已保存: {excel_path}")
        return excel_path


def extract_towers_standalone(input_file: str,
                              output_dir: str = "output",
                              max_memory_percent: int = 30,
                              max_threads: int = 6,
                              eps: float = 10.0,
                              min_samples: int = 50,
                              min_height: float = 12.0,
                              max_width: float = 60.0,
                              min_width: float = 6.0,
                              aspect_ratio_threshold: float = 0.6) -> List[Dict]:
    """
    独立运行的杆塔提取函数

    参数:
        input_file: 输入LAS文件路径
        output_dir: 输出目录
        max_memory_percent: 最大内存使用百分比 (默认30%)
        max_threads: 最大线程数 (默认6)
        eps: DBSCAN聚类半径
        min_samples: 最小样本数
        min_height: 最小杆塔高度
        max_width: 最大杆塔宽度
        min_width: 最小杆塔宽度
        aspect_ratio_threshold: 长宽比阈值

    返回:
        检测到的杆塔列表
    """

    print("=" * 60)
    print("🏗️ 独立杆塔提取工具")
    print("=" * 60)

    start_time = time.time()

    # 初始化提取器
    extractor = StandaloneTowerExtractor(max_memory_percent, max_threads)

    try:
        # 1. 读取文件
        points, header_info = extractor.read_las_file(input_file)

        # 2. 高度过滤
        filtered_points = extractor.height_filter(points)
        del points  # 释放原始点云内存
        gc.collect()

        # 3. 自适应降采样
        sampled_points = extractor.adaptive_downsample(filtered_points)
        if len(sampled_points) < len(filtered_points):
            del filtered_points
            filtered_points = sampled_points
        gc.collect()

        # 4. 聚类分析
        labels = extractor.cluster_points(filtered_points, eps, min_samples)

        # 5. 杆塔检测
        towers = extractor.detect_towers(
            filtered_points, labels,
            min_height, max_width, min_width, aspect_ratio_threshold
        )

        # 6. 去重
        unique_towers = extractor.remove_duplicates(towers)

        # 7. 保存结果
        output_file = extractor.save_results(unique_towers, header_info, output_dir)

        # 总结
        elapsed_time = time.time() - start_time
        final_memory = extractor.monitor_memory("处理完成后")

        print("\n" + "=" * 60)
        print("✅ 处理完成!")
        print(f"⏱️  总用时: {elapsed_time:.1f}秒")
        print(f"🏗️  检测到杆塔: {len(unique_towers)} 个")
        print(f"💾 最终内存使用: {final_memory:.1f}%")
        if output_file:
            print(f"📄 结果文件: {output_file}")
        print("=" * 60)

        return unique_towers

    except Exception as e:
        print(f"\n❌ 处理失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        # 最终内存清理
        gc.collect()


def main():
    """命令行主函数"""
    parser = argparse.ArgumentParser(description="独立运行的杆塔提取工具")
    parser.add_argument("input", nargs="?", help="输入LAS文件路径")
    parser.add_argument("-o", "--output", default="output", help="输出目录 (默认: output)")
    parser.add_argument("-m", "--memory", type=int, default=30, help="最大内存使用百分比 (默认: 30)")
    parser.add_argument("-t", "--threads", type=int, default=6, help="最大线程数 (默认: 6)")
    parser.add_argument("--eps", type=float, default=10.0, help="聚类半径 (默认: 10.0)")
    parser.add_argument("--min-samples", type=int, default=50, help="最小样本数 (默认: 50)")
    parser.add_argument("--min-height", type=float, default=12.0, help="最小杆塔高度 (默认: 12.0)")
    parser.add_argument("--max-width", type=float, default=60.0, help="最大杆塔宽度 (默认: 60.0)")

    args = parser.parse_args()

    if not args.input:
        # 交互式模式
        print("🔍 交互式模式")
        print("请输入LAS文件路径:")
        input_file = input().strip().strip('"')  # 去除可能的引号
    else:
        input_file = args.input

    if not os.path.exists(input_file):
        print(f"❌ 文件不存在: {input_file}")
        return

    # 运行提取
    towers = extract_towers_standalone(
        input_file=input_file,
        output_dir=args.output,
        max_memory_percent=args.memory,
        max_threads=args.threads,
        eps=args.eps,
        min_samples=args.min_samples,
        min_height=args.min_height,
        max_width=args.max_width
    )

    if towers:
        print(f"\n🎉 成功检测到 {len(towers)} 个杆塔!")
        print("详细结果请查看输出的Excel文件。")
    else:
        print("\n😔 未检测到杆塔，请尝试调整参数。")


if __name__ == "__main__":
    main()