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
        lines_count = len(resp.text.strip().split('\n'))
        print(f'  ✅ [{label}] 成功 ({lines_count} 行)')
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

    # 2. 调试测试：尝试不同格式和过滤条件
    queries = [
        # format/tle 是 2 行格式（无卫星名）
        ('/class/gp/MEAN_MOTION/%3E11/limit/3/format/tle', 'gp + MEAN_MOTION (2行格式)'),
        # format/3le 是 3 行格式（含卫星名）
        ('/class/gp/MEAN_MOTION/%3E11/limit/3/format/3le', 'gp + MEAN_MOTION (3行格式)'),
        # MEAN_MOTION + EPOCH 组合过滤 (LEO + 最近30天)
        ('/class/gp/MEAN_MOTION/%3E11/EPOCH/%3Enow-30/limit/3/format/3le', 'gp + MEAN_MOTION + EPOCH (3行格式)'),
        # 纯 EPOCH 过滤（所有轨道，最近7天）
        ('/class/gp/EPOCH/%3Enow-7/limit/3/format/3le', 'gp + EPOCH'),
        # 不加任何过滤
        ('/class/gp/limit/3/format/3le', 'gp 基础 (3行格式)'),
    ]

    results = {}
    for path, label in queries:
        success, text = try_query(session, path, label)
        results[label] = (success, text)
        if success and text:
            # 显示前3行看看格式
            lines = text.strip().split('\n')
            for i, l in enumerate(lines[:3]):
                print(f'    第{i+1}行: {l[:80]}')
        print()

    # 3. 选择最佳查询获取完整数据
    print('=' * 50)
    print('选择最佳查询获取完整数据...')
    print('=' * 50)

    tle_text = None

    # 按优先级尝试查询方案
    candidates = [
        # 方案 A: MEAN_MOTION + EPOCH (LEO + 近30天，按更新时间倒序)
        ('gp + MEAN_MOTION + EPOCH (3行格式)',
         '/class/gp/MEAN_MOTION/%3E11/EPOCH/%3Enow-30/orderby/EPOCH%20desc/limit/10000/format/3le'),
        # 方案 B: 只有 MEAN_MOTION (所有历史 LEO 卫星，按 ID 倒序)
        ('gp + MEAN_MOTION (3行格式)',
         '/class/gp/MEAN_MOTION/%3E11/orderby/NORAD_CAT_ID%20desc/limit/10000/format/3le'),
        # 方案 C: 只加 EPOCH (最近7天所有卫星，按更新时间倒序)
        ('gp + EPOCH',
         '/class/gp/EPOCH/%3Enow-7/orderby/EPOCH%20desc/limit/10000/format/3le'),
    ]

    for label_key, path in candidates:
        if label_key in results and results[label_key][0]:
            print(f'✅ 使用 "{label_key}" 查询')
            print(f'   GET /basicspacedata/query{path}')
            resp = session.get(f'https://www.space-track.org/basicspacedata/query{path}')
            if resp.status_code == 200 and resp.text.strip():
                tle_text = resp.text.strip()
                break
            else:
                print(f'   ❌ HTTP {resp.status_code}')
                if resp.text:
                    print(f'   {resp.text[:200]}')

    if not tle_text:
        print('❌ 查询结果为空')
        sys.exit(1)

    # 4. 统计
    lines = [l for l in tle_text.split('\n') if l.strip()]
    # 3行格式：卫星名行 + 行1 + 行2
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

    # 6. 显示前6行（2颗卫星）
    print('--- 前6行 ------------------')
    for i, line in enumerate(lines[:6]):
        print(f'{i+1:2d}: {line[:80]}')
    print('-----------------------------')

    # 7. 检查星座（卫星名在每组的第1行）
    name_lines = lines[0::3]  # 每3行的第1行是卫星名
    qf_count = sum(1 for l in name_lines if 'QIANFAN' in l.upper())
    gw_count = sum(1 for l in name_lines if 'GW' in l.upper() or 'GUOWANG' in l.upper())
    starlink_count = sum(1 for l in name_lines if 'STARLINK' in l.upper())
    oneweb_count = sum(1 for l in name_lines if 'ONEWEB' in l.upper())
    print(f'🔍 QIANFAN: {qf_count} 颗')
    print(f'🔍 GW: {gw_count} 颗')
    print(f'🔍 Starlink: {starlink_count} 颗')
    print(f'🔍 OneWeb: {oneweb_count} 颗')

    if qf_count == 0 and starlink_count == 0:
        print('⚠️ 没有识别到任何已知星座卫星')
        print('   可能原因: 3le 格式不包含卫星名，或时间过滤太严格')
        # 显示所有卫星名帮助调试
        print('--- 所有卫星名(前20) ------')
        for l in name_lines[:20]:
            print(f'   [{l[:60]}]')
        print('----------------------------')


if __name__ == '__main__':
    main()