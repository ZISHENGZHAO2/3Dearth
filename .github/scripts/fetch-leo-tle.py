#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 space-track.org 获取低轨卫星 TLE 数据（使用 requests）"""

import os
import re
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

    # 7. 详细分类统计（卫星名在每组的第1行）
    name_lines = lines[0::3]  # 每3行的第1行是卫星名

    print()
    print('=' * 50)
    print('📊 卫星详细分类')
    print('=' * 50)

    # -- 已知星座 --
    constellations = {
        'Starlink':    'STARLINK',
        'OneWeb':      'ONEWEB',
        '千帆(QIANFAN)': 'QIANFAN',
        '国网(GW)':     r'(?:^|\s)GW(?:[-\s]|\d|$)',
        '国网(GUOWANG)': 'GUOWANG',
        'Iridium':     'IRIDIUM',
        'Globalstar':  'GLOBALSTAR',
        'Orbcomm':     'ORBCOMM',
        'Kuiper':      'KUIPER',
        'Spire':       'LEMUR',
        'Swarm':       'SWARM',
        'AST Space':   r'AST\b',
        'Planet Labs': 'PLANET',
        'ISS':         r'\bISS\b',
        '天象(TIANMU)': 'TIANMU',
        '风云(FY)':     'FENGYUN',
        '遥感(YG)':     'YAOGAN',
        '高分(GF)':     'GAOFEN',
        '北斗(BD)':     'BEIDOU',
        '吉林(JILIN)':  'JILIN',
        '珞珈(LUOJIA)': 'LUOJIA',
        '天智(TIANZHI)': 'TIANZHI',
        'TZ卫星':       r'\bTZ[- ]',
    }
    print('--- 已知星座/卫星 ---')
    for label, pattern in sorted(constellations.items()):
        count = sum(1 for l in name_lines if re.search(pattern, l, re.IGNORECASE))
        if count > 0:
            print(f'  {label:20s}  {count:5d} 颗')

    # -- 按卫星类型分组 --
    categories = {
        '碎片 (DEB)':         r'\bDEB\b',
        '火箭体 (R/B)':       r'\bR/B\b',
        '上面级 (PKM)':       r'\bPKM\b',
        '有效载荷 (PLD)':     r'\bPLD\b',
        '其他物体 (TBA/UNK)': r'\b(TBA|UNK)\b',
    }
    print('--- 按卫星类型 ---')
    debris_count = 0
    for label, pattern in categories.items():
        count = sum(1 for l in name_lines if re.search(pattern, l, re.IGNORECASE))
        if count > 0:
            print(f'  {label:25s}  {count:5d} 颗')
            debris_count += count
    print(f'  {"其他(含正常运行卫星)":25s}  {len(name_lines) - debris_count:5d} 颗')

    # -- NORAD ID 范围 --
    # 从 TLE 行1 提取 NORAD ID (第3-7字符)
    norad_ids = []
    for l in lines[1::3]:  # TLE 行1
        try:
            norad_ids.append(int(l[2:7].strip()))
        except (ValueError, IndexError):
            pass
    if norad_ids:
        print(f'--- 轨道信息 ---')
        print(f'  NORAD ID 范围:  {min(norad_ids):06d} ~ {max(norad_ids):06d}')

    # -- MEAN_MOTION 范围 --
    motions = []
    for l in lines[2::3]:  # TLE 行2
        try:
            # 第53-63字符约是 MEAN_MOTION
            val = float(l[52:63].strip())
            motions.append(val)
        except (ValueError, IndexError):
            pass
    if motions:
        print(f'  MEAN_MOTION 范围: {min(motions):.2f} ~ {max(motions):.2f} rev/day')
        print(f'  轨道周期范围: {format(1440/max(motions), ".1f")} ~ {format(1440/min(motions), ".1f")} 分钟')

    # -- 前10和后10卫星名 --
    print('--- 最早10颗卫星(按更新时间) ---')
    for l in name_lines[-10:]:
        print(f'  [{l[:70].strip()}]')
    print('--- 最新10颗卫星(按更新时间) ---')
    for l in name_lines[:10]:
        print(f'  [{l[:70].strip()}]')

    # -- 如果 GW 为空，搜索所有中文相关卫星 --
    gw_count = sum(1 for l in name_lines if re.search(r'(?:^|\s)GW(?:[-\s]|\d|$)', l, re.IGNORECASE))
    guowang_count = sum(1 for l in name_lines if re.search('GUOWANG', l, re.IGNORECASE))
    if gw_count == 0 and guowang_count == 0:
        print()
        print('🔍 GW 搜索为空，正在探索数据中所有卫星命名规律...')
        # 收集所有含 CHINA 的卫星名
        china_names = [l.strip() for l in name_lines if re.search(r'\bCHINA\b', l, re.IGNORECASE)]
        if china_names:
            print(f'--- 含 "CHINA" 的卫星名 ({len(china_names)} 颗) ---')
            for name in china_names[:15]:
                print(f'  [{name[:70]}]')
            if len(china_names) > 15:
                print(f'  ... 还有 {len(china_names)-15} 颗')
        # 收集常见中文卫星前缀
        chinese_prefixes = {
            'SJ (实践)':     r'\bSJ[- ]',
            'XS (行式)':     r'\bXS[- ]',
            'CQ (重庆)':     r'\bCQ[- ]',
            'TKS':          r'\bTKS',
            'CX (创新)':     r'\bCX[- ]',
            'SY (试验)':     r'\bSY[- ]',
            'JS':           r'\bJS[- ]',
        }
        found_prefixes = False
        for label, pat in chinese_prefixes.items():
            count = sum(1 for l in name_lines if re.search(pat, l, re.IGNORECASE))
            if count > 0:
                if not found_prefixes:
                    print('--- 常见中文卫星前缀 ---')
                    found_prefixes = True
                print(f'  {label:15s}: {count} 颗')
        if not found_prefixes:
            print('  (未找到常见中文卫星前缀)')
        # 搜索名字中包含数字+字母组合、可能是实验星的
        print('--- 名字含 "OBJECT" 的实验星 ---')
        obj_count = sum(1 for l in name_lines if 'OBJECT' in l.upper())
        print(f'  OBJECT: {obj_count} 颗')
        print('--- 名字含 "TECH" 或 "TEST" 的技术试验星 ---')
        tech_count = sum(1 for l in name_lines if re.search(r'\b(TECH|TEST|DEMO)\b', l, re.IGNORECASE))
        print(f'  TECH/TEST/DEMO: {tech_count} 颗')

    # -- 用户自定义搜索 --
    print()
    print('--- 自定义搜索 ---')
    custom_keywords = [
        '天智', 'TIANZHI', 'TZ-', 'TZ ',
        '紫丁香', 'LILACSAT', 'LILAC',
        '银河', 'YINHE', 'MILKY WAY',
        '星网', 'XINGWANG',
        'SATRIA',
    ]
    found_custom = False
    for kw in custom_keywords:
        count = sum(1 for l in name_lines if re.search(kw, l, re.IGNORECASE))
        if count > 0:
            found_custom = True
            print(f'  "{kw}": {count} 颗')
            matches = [l.strip() for l in name_lines if re.search(kw, l, re.IGNORECASE)]
            for m in matches[:3]:
                print(f'    例: [{m[:70]}]')
    if not found_custom:
        # 模糊搜索：找名字较短、可能是实验星的卫星
        print('  (未找到匹配，显示一些可能相关的实验星)')
        short_names = [l.strip() for l in name_lines
                       if len(l.replace('0 ', '').strip()) < 15
                       and not re.search(r'(DEB|R/B|PKM|STARLINK|ONEWEB|IRIDIUM|FENGYUN|YAOGAN)', l, re.IGNORECASE)]
        for m in short_names[:10]:
            print(f'    实验星: [{m[:70]}]')


if __name__ == '__main__':
    main()