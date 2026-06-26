#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 space-track.org 获取低轨卫星 TLE 数据"""

import os
import sys

import spacetrack.operators as op
from spacetrack import SpaceTrackClient

def main():
    username = os.environ.get('SPACETRACK_USER')
    password = os.environ.get('SPACETRACK_PASS')

    if not username or not password:
        print('❌ 请设置 SPACETRACK_USER 和 SPACETRACK_PASS 环境变量')
        sys.exit(1)

    print(f'🔑 用户名: {username}')

    try:
        st = SpaceTrackClient(username, password)
        print('✅ 登录成功')
    except Exception as e:
        print(f'❌ 登录失败: {e}')
        sys.exit(1)

    # MEAN_MOTION > 11 表示低轨卫星
    # MEAN_MOTION 单位是 rev/day，>11 意味着轨道周期 < 130 分钟 (LEO 一般低于 2000km)
    tle_data = st.tle_latest(
        ordinal=1,
        mean_motion=op.greater_than(11),
        limit=2000,
        orderby='norad_cat_id asc',
        format='tle'
    )

    if not tle_data:
        print('❌ 查询结果为空')
        sys.exit(1)

    lines = [line.strip() for line in tle_data.split('\n') if line.strip()]
    print(f'📊 获取到 {len(lines) // 3} 颗低轨卫星')

    # 写入文件
    output_path = 'app/src/main/assets/qianfan_tle_backup.txt'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(tle_data)
        if not tle_data.endswith('\n'):
            f.write('\n')

    print(f'✅ 已写入 {output_path}')
    print(f'📄 大小: {os.path.getsize(output_path)} 字节')

    # 显示前10行
    print('--- 前10行 ------------------')
    for i, line in enumerate(lines[:10]):
        print(f'{i+1:2d}: {line}')
    print('-----------------------------')

    # 检查是否有 QIANFAN
    qf_count = sum(1 for line in lines if 'QIANFAN' in line.upper())
    print(f'🔍 QIANFAN 卫星数: {qf_count}')

if __name__ == '__main__':
    main()