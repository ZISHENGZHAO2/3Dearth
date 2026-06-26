#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 space-track.org 获取低轨卫星 TLE 数据（使用 requests，不依赖 spacetrack 库）"""

import os
import sys
import requests


def main():
    username = os.environ.get('SPACETRACK_USER')
    password = os.environ.get('SPACETRACK_PASS')

    if not username or not password:
        print('❌ 请设置 SPACETRACK_USER 和 SPACETRACK_PASS 环境变量')
        sys.exit(1)

    # 1. 登录
    session = requests.Session()
    login_url = 'https://www.space-track.org/ajaxauth/login'
    login_data = {'identity': username, 'password': password}

    resp = session.post(login_url, data=login_data)
    if resp.status_code != 200:
        print(f'❌ 登录失败 (HTTP {resp.status_code}): {resp.text[:100]}')
        sys.exit(1)
    print('✅ 登录成功')

    # 2. 查询低轨卫星 TLE
    #    class=gp (General Perturbations，包含 TLE 数据)
    #    ORDINAL=1  → 只取每组最新数据
    #    MEAN_MOTION > 11  → 轨道周期 < 130min，即低轨卫星
    #    limit=2000 → 最多 2000 颗
    query_url = (
        'https://www.space-track.org/basicspacedata/query'
        '/class/gp'
        '/ORDINAL/1'
        '/MEAN_MOTION/%3E11'
        '/orderby/NORAD_CAT_ID%20asc'
        '/limit/2000'
        '/format/tle'
    )

    print(f'🔍 正在查询低轨卫星 ...')
    resp = session.get(query_url)

    if resp.status_code != 200:
        print(f'❌ 查询失败 (HTTP {resp.status_code}):')
        print(resp.text[:300])
        sys.exit(1)

    tle_text = resp.text.strip()

    if not tle_text:
        print('❌ 查询结果为空')
        sys.exit(1)

    # 3. 统计
    lines = [l for l in tle_text.split('\n') if l.strip()]
    # TLE 中卫星名行可能不是纯大写字母开头（可能有数字），但标准的 TLE 格式有：
    #   第1行：卫星名
    #   第2行：以 "1 " 开头
    #   第3行：以 "2 " 开头
    # 所以卫星数量 ≈ (总行数) // 3
    sat_count = len(lines) // 3
    print(f'📊 获取到约 {sat_count} 颗低轨卫星')

    # 4. 写入文件
    output_path = 'app/src/main/assets/qianfan_tle_backup.txt'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(tle_text)
        if not tle_text.endswith('\n'):
            f.write('\n')

    print(f'✅ 已写入 {output_path}')
    print(f'📄 大小: {os.path.getsize(output_path)} 字节')

    # 5. 显示前10行
    print('--- 前10行 ------------------')
    for i, line in enumerate(lines[:10]):
        print(f'{i+1:2d}: {line}')
    print('-----------------------------')

    # 6. 检查星座
    qf_count = sum(1 for l in lines if 'QIANFAN' in l.upper())
    gw_count = sum(1 for l in lines if 'GW' in l.upper() or 'GUOWANG' in l.upper())
    starlink_count = sum(1 for l in lines if 'STARLINK' in l.upper())
    oneweb_count = sum(1 for l in lines if 'ONEWEB' in l.upper())
    print(f'🔍 QIANFAN: {qf_count} 颗')
    print(f'🔍 GW: {gw_count} 颗')
    print(f'🔍 Starlink: {starlink_count} 颗')
    print(f'🔍 OneWeb: {oneweb_count} 颗')


if __name__ == '__main__':
    main()