#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 space-track.org 获取低轨卫星 TLE 数据（使用 requests）"""

import os
import sys
import requests


def try_query(session, url_path, label):
    """尝试一个查询，返回 (success, text)"""
    url = f'https://www.space-track.org/basicspacedata/query{url_path}'
    print(f'  ⏳ [{label}] GET {url}')
    resp = session.get(url)
    if resp.status_code == 200 and resp.text.strip():
        print(f'  ✅ [{label}] 成功 ({len(resp.text.strip().split(chr(10)))} 行)')
        return True, resp.text.strip()
    else:
        print(f'  ❌ [{label}] HTTP {resp.status_code}')
        return False, None


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

    # 2. 逐步尝试不同的查询组合，找出可用的
    queries = [
        # 简单测试 - 不加任何过滤
        ('/class/gp/limit/3/format/tle', 'gp 基础测试'),
        # 去掉 ORDINAL（gp 可能不支持）
        ('/class/gp/MEAN_MOTION/%3E11/limit/3/format/tle', 'gp + MEAN_MOTION'),
        # 只加 ORDINAL
        ('/class/gp/ORDINAL/1/limit/3/format/tle', 'gp + ORDINAL'),
        # 按日期过滤（最近7天）
        ('/class/gp/EPOCH/%3Enow-7/limit/3/format/tle', 'gp + EPOCH'),
        # 不带 limit 测试
        ('/class/gp/MEAN_MOTION/%3E11/NORAD_CAT_ID/40069/format/tle', 'gp + MEAN_MOTION + NORAD_CAT_ID'),
    ]

    results = {}
    for path, label in queries:
        success, text = try_query(session, path, label)
        results[label] = (success, text)
        print()  # 空行分隔

    # 3. 选择可用的查询方式，获取完整数据
    print('=' * 50)
    print('选择最佳查询获取完整数据...')
    print('=' * 50)

    tle_text = None

    # 优先用带 MEAN_MOTION 过滤的
    for label_key in ['gp + MEAN_MOTION', 'gp + MEAN_MOTION + NORAD_CAT_ID']:
        if label_key in results and results[label_key][0]:
            print(f'✅ 使用 "{label_key}" 查询')
            # 构造完整查询（去掉 limit/3）
            path = '/class/gp/MEAN_MOTION/%3E11/limit/5000/format/tle'
            print(f'   GET /basicspacedata/query{path}')
            resp = session.get(f'https://www.space-track.org/basicspacedata/query{path}')
            if resp.status_code == 200 and resp.text.strip():
                tle_text = resp.text.strip()
                break
            else:
                print(f'   ❌ HTTP {resp.status_code}')

    # 如果 MEAN_MOTION 不行，用 EPOCH 过滤（最近7天的所有数据）
    if not tle_text and 'gp + EPOCH' in results and results['gp + EPOCH'][0]:
        print('✅ 使用 EPOCH 查询（最近7天所有卫星）')
        path = '/class/gp/EPOCH/%3Enow-7/limit/5000/format/tle'
        print(f'   GET /basicspacedata/query{path}')
        resp = session.get(f'https://www.space-track.org/basicspacedata/query{path}')
        if resp.status_code == 200 and resp.text.strip():
            tle_text = resp.text.strip()

    # 最后兜底：不加任何过滤（获取所有数据）
    if not tle_text:
        print('⚠️ 使用无过滤查询（所有卫星）')
        path = '/class/gp/limit/5000/format/tle'
        print(f'   GET /basicspacedata/query{path}')
        resp = session.get(f'https://www.space-track.org/basicspacedata/query{path}')
        if resp.status_code == 200 and resp.text.strip():
            tle_text = resp.text.strip()

    if not tle_text:
        print('❌ 所有查询都失败了')
        sys.exit(1)

    # 4. 统计
    lines = [l for l in tle_text.split('\n') if l.strip()]
    sat_count = len(lines) // 3
    print(f'📊 获取到约 {sat_count} 颗卫星')

    # 5. 写入文件
    output_path = 'app/src/main/assets/qianfan_tle_backup.txt'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(tle_text)
        if not tle_text.endswith('\n'):
            f.write('\n')

    print(f'✅ 已写入 {output_path}')
    print(f'📄 大小: {os.path.getsize(output_path)} 字节')

    # 6. 显示前10行
    print('--- 前10行 ------------------')
    for i, line in enumerate(lines[:10]):
        print(f'{i+1:2d}: {line}')
    print('-----------------------------')

    # 7. 检查星座
    qf_count = sum(1 for l in lines if 'QIANFAN' in l.upper())
    gw_count = sum(1 for l in lines if 'GW' in l.upper() or 'GUOWANG' in l.upper())
    starlink_count = sum(1 for l in lines if 'STARLINK' in l.upper())
    oneweb_count = sum(1 for l in lines if 'ONEWEB' in l.upper())
    print(f'🔍 QIANFAN: {qf_count} 颗')
    print(f'🔍 GW: {gw_count} 颗')
    print(f'🔍 Starlink: {starlink_count} 颗')
    print(f'🔍 OneWeb: {oneweb_count} 颗')

    # 8. 输出低轨卫星占比（如果用了无过滤查询）
    if 'MEAN_MOTION' not in path:
        leo_count = sum(1 for l in lines[:sat_count*3] if l.strip() and not l.startswith('1 ') and not l.startswith('2 '))
        print(f'📌 所有卫星: {sat_count} 颗')
        print('💡 建议: 如果查询没有 MEAN_MOTION 过滤，数据可能包含 GEO/MEO 卫星')


if __name__ == '__main__':
    main()