# Point Cloud Tower Tool - 构建说明

## 项目简介
竣工图模型与激光点云数据自动校对与优化工具 - 专业的电力工程点云处理软件

## 功能特性
- 🔍 激光点云数据导入和处理 (LAS/LAZ格式)
- 🏗️ GIM模型文件解析和杆塔信息提取
- 🎯 自动去除地物并提取杆塔结构
- 🖥️ 3D可视化显示点云和杆塔
- ⚙️ 点云与GIM模型数据的智能匹配和校对
- 💾 生成校对后的GIM文件

## 构建exe文件

### 方法一：使用批处理文件（推荐）
1. 确保已安装Python 3.8+
2. 双击运行 `build.bat`
3. 程序会自动安装依赖并构建exe文件
4. 构建完成后，exe文件位于 `dist/PointCloudTowerTool/` 目录

### 方法二：手动构建
1. 安装依赖：
   ```bash
   pip install -r requirements_build.txt
   ```

2. 使用PyInstaller构建：
   ```bash
   pyinstaller --clean build_spec.py
   ```

3. 可执行文件将生成在 `dist/PointCloudTowerTool/` 目录中

## 技术架构
- **GUI框架**: PyQt5
- **3D处理**: Open3D + VTK
- **数据处理**: NumPy + Pandas
- **点云格式**: LASpy
- **文件压缩**: Py7zr
- **坐标转换**: PyProj

## 使用说明
1. 启动程序后，按照界面按钮顺序操作：
   - 导入GIM → 导入点云 → 去除地物 → 提取杆塔 → 匹配 → 校对 → 保存
2. 支持的文件格式：
   - 点云文件：.las, .laz
   - 模型文件：.gim
3. 处理结果可导出为更新后的GIM文件

## 注意事项
- 首次运行可能需要较长时间初始化
- 建议在处理大型点云文件时预留足够内存
- 生成的exe文件包含所有必要依赖，可独立运行

## 系统要求
- Windows 10/11 64位
- 内存：8GB以上推荐
- 硬盘：2GB可用空间
- 支持OpenGL 3.3+的显卡
