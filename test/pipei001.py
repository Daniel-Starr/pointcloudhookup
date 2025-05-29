import pandas as pd
from math import radians, sin, cos, sqrt, asin

# Haversine 距离函数（返回米）
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # 地球半径，单位：米
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * asin(sqrt(a))

# 目标经纬度点（你提供的4个）
target_points = [
    ('P79', 28.548474140836877, 113.51342253295904),
    ('P95', 28.512143799167948, 113.46679607250084),
    ('P6', 28.80187265878493, 113.50607353186189),
    ('P105', 28.498050034396293, 113.4323778385627)
]

# 读取 Excel 数据
excel_path = 'tower.xlsx'  # 请根据需要替换为你的文件路径
df = pd.read_excel(excel_path)

# 匹配逻辑：寻找与目标点距离小于 100 米的最接近点
matches = []
for label, lat0, lon0 in target_points:
    closest = None
    min_dist = float('inf')
    for _, row in df.iterrows():
        lat, lon = row['纬度'], row['经度']
        dist = haversine(lat0, lon0, lat, lon)
        if dist < 100 and dist < min_dist:
            closest = row.to_dict()
            min_dist = dist
    if closest:
        matches.append({
            '目标编号': label,
            '目标纬度': lat0,
            '目标经度': lon0,
            '匹配编号': closest['杆塔编号'],
            '匹配纬度': closest['纬度'],
            '匹配经度': closest['经度'],
            '距离（米）': min_dist
        })
    else:
        matches.append({
            '目标编号': label,
            '目标纬度': lat0,
            '目标经度': lon0,
            '匹配编号': '未找到',
            '匹配纬度': '',
            '匹配经度': '',
            '距离（米）': ''
        })

# 输出匹配结果 DataFrame
result_df = pd.DataFrame(matches)
print(result_df)

# 可选：保存为 Excel 文件
result_df.to_excel('matched_results.xlsx', index=False)
print("✅ 匹配结果已保存为 matched_results.xlsx")
