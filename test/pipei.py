from data1 import data1
from data2 import data2

import numpy as np


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # 地球半径（单位：米）
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)

    a = np.sin(delta_phi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

def pipei(arr1, arr2):
    for i in arr2:
        lng1 = float(i['lng'])
        lat1 = float(i['lat'])
        for j in arr1:
            lng2 = float(j['lng'])
            lat2 = float(j['lat'])
            dist = haversine(lat1, lng1, lat2, lng2)
            if dist < 0.00001:
                cbm_path = j['cbm_path']
                with open(cbm_path, 'r', encoding='utf-8') as f:
                    print('txt', f.read())


pipei(data1,data2)