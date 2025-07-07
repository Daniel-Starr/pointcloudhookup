import laspy
from pyproj import Transformer
import numpy as np
import os
import time


def convert_las_coordinates(input_path, output_dir=None, batch_size=1000000):
    """
    完整转换LAS文件坐标系（CGCS2000转WGS84）

    参数:
        input_path: 输入LAS文件路径
        output_dir: 输出目录（None则自动创建）
        batch_size: 分批处理点数（内存优化）
    """
    # 验证输入文件
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    # 准备输出路径
    basename = os.path.basename(input_path)
    output_path = os.path.join(output_dir or os.path.dirname(input_path),
                               f"converted_{basename}")

    try:
        # 记录开始时间
        start_time = time.time()

        # 1. 读取LAS文件
        with laspy.open(input_path) as las:
            crs = las.header.parse_crs()
            print(f"▌ 文件坐标系: {crs if crs else '未定义（将使用EPSG:4547）'}")
            print(f"▌ 点格式: {las.header.point_format.id}")

            # 2. 创建坐标转换器
            transformer = Transformer.from_crs("EPSG:4547", "EPSG:4326", always_xy=True)

            # 3. 准备输出文件
            out_header = las.header.copy()
            out_file = laspy.LasData(out_header)

            # 4. 分批处理坐标转换
            total_points = las.header.point_count
            print(f"▌ 开始转换 {total_points:,} 个点...")

            point_count = 0
            for points in las.chunk_iterator(batch_size):
                # 获取坐标（正确访问方式）
                x = points.x
                y = points.y
                z = points.z

                # 执行坐标转换
                lon, lat = transformer.transform(x, y)

                # 创建新点集
                new_points = np.zeros(len(points), dtype=out_file.point_format.dtype)

                # 设置坐标
                new_points['X'] = lon
                new_points['Y'] = lat
                new_points['Z'] = z

                # 复制所有其他维度
                for dim in out_file.point_format.dimensions:
                    dim_name = dim.name
                    if dim_name not in ['X', 'Y', 'Z']:
                        try:
                            new_points[dim_name] = getattr(points, dim_name)
                        except AttributeError:
                            continue

                # 添加到输出文件
                out_file.points = np.append(out_file.points, new_points)
                point_count += len(points)

                # 显示进度
                elapsed = time.time() - start_time
                pts_per_sec = point_count / elapsed if elapsed > 0 else 0
                print(f"▌ 进度: {point_count}/{total_points} ({point_count / total_points:.1%}) | "
                      f"速度: {pts_per_sec:,.0f} 点/秒", end='\r')

            # 5. 更新坐标系并保存
            out_file.header.update_crs("EPSG:4326")
            out_file.write(output_path)

            # 计算总耗时
            total_time = time.time() - start_time
            print(f"\n✔ 转换完成！耗时: {total_time:.2f} 秒 | "
                  f"平均速度: {total_points / total_time:,.0f} 点/秒")
            print(f"结果已保存到: {output_path}")

            # 返回转换后的坐标示例
            sample_idx = np.random.randint(0, total_points, 3)
            return np.column_stack([
                out_file.x[sample_idx],
                out_file.y[sample_idx],
                out_file.z[sample_idx]
            ])

    except Exception as e:
        print(f"\n✖ 转换失败: {str(e)}")
        if os.path.exists(output_path):
            os.remove(output_path)
        raise


if __name__ == '__main__':
    # 使用示例
    input_las = r"E:\pointcloudhookup\output\point_2.las"

    try:
        samples = convert_las_coordinates(
            input_path=input_las,
            output_dir=r"E:\pointcloudhookup\output\converted",
            batch_size=500000
        )

        print("\n示例坐标（经度, 纬度, 高程）：")
        for i, coord in enumerate(samples):
            print(f"点{i + 1}: {coord[0]:.6f}, {coord[1]:.6f}, {coord[2]:.2f}")

    except Exception as e:
        print(f"程序执行出错: {str(e)}")