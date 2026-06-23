# 基于全球 TEC 计算

## 1. 项目简介

本项目基于 `TemporalMemoryEOF-CatBoost` 模型，实现：

- 单个时刻全球电离层 TEC 地图计算
- 全球 TEC 可视化
- TEC 网格数据输出
- YAML 参数配置
---

# 2. 工程目录结构

建议目录结构如下：

```text
project_root/
│
├── demo_memory_model_tec_single_time.py
├── memory_tec_single_time_config.yaml
├── README_single_time_CN.md
│
├── uploads/
│   ├── eof_maps.csv
│   ├── tec_mean.csv
│   ├── pc_1.csv
│   ├── pc_2.csv
│   └── pc_3.csv
│
├── outputs/
│   └── TemporalMemoryEOF_climatology/
│       └── saved_models/
│           └── TemporalMemoryEOF-CatBoost.pkl
│
└── figures/
```

---

# 3. 模型所需文件

## 3.1 EOF 数据文件

请放置到：

```text
./uploads/
```

需要文件：

| 文件名 | 说明 |
|---|---|
| eof_maps.csv | EOF 基函数 |
| tec_mean.csv | TEC 平均场 |
| pc_1.csv | 主成分数据 |
| pc_2.csv | 主成分数据 |
| pc_3.csv | 主成分数据 |

---

## 3.2 MEMORY_MODEL 模型文件

请放置到：

```text
./outputs/TemporalMemoryEOF_climatology/saved_models/
```

模型文件：

```text
TemporalMemoryEOF-CatBoost.pkl
```

---

# 4. Python 环境

推荐：

- Python 3.9+
- Conda 环境

安装依赖：

```bash
pip install numpy pandas matplotlib cartopy pyyaml catboost
```

Windows 推荐：

```bash
conda install -c conda-forge cartopy
```

---

# 5. YAML 配置文件

配置文件：

```text
memory_tec_single_time_config.yaml
```

示例：

```yaml
year: 2025
doy: 1
ut_hour: 12

plot:
  vmin: 0
  vmax: 100
  cmap: jet

output:
  figure_dir: ./figures
  figure_name: memory_tec_2025001_12UT.png
  save_npz: true

drivers:
  f107: 120
  f107a: 118
  dst: -20
  ap: 12
  kp: 2.0

memory_lags:

  dst_lag_1: -18
  dst_lag_3: -16
  dst_lag_6: -14
  dst_lag_12: -10
  dst_lag_24: -8

  ap_lag_1: 10
  ap_lag_3: 9
  ap_lag_6: 8
  ap_lag_12: 7
  ap_lag_24: 6

  kp_lag_1: 1.8
  kp_lag_3: 1.6
  kp_lag_6: 1.5
  kp_lag_12: 1.3
  kp_lag_24: 1.0

solar_lags:

  f107_lag_24: 118
  f107_lag_72: 117
  f107_lag_168: 115
  f107_lag_648: 110

  f107a_lag_24: 118
  f107a_lag_72: 117
  f107a_lag_168: 116
  f107a_lag_648: 112
```

---

# 6. 运行方法

运行：

```bash
python demo_tec.py --config config.yaml
```

---

# 7. 输出结果

## 7.1 TEC 图像

输出到：

```text
./figures/
```

例如：

```text
memory_tec_2025001_12UT.png
```

---

## 7.2 TEC 网格数据

若：

```yaml
save_npz: true
```

则输出：

```text
memory_tec_2025001_12UT.npz
```

包含：

| 变量 | 说明 |
|---|---|
| tec | TEC 网格 |
| lats | 纬度数组 |
| lons | 经度数组 |

---

# 8. TEC 网格说明

默认：

- 纬度：71 点
- 经度：73 点

对应：

- 纬向分辨率：2.5°
- 经向分辨率：5°

---

# 9. TEC 单位

输出单位：

```text
TECU
```

其中：

```text
1 TECU = 10^16 electrons / m²
```

---

# 10. 模型输入参数说明

## 10.1 当前时刻驱动参数

| 参数 | 说明 |
|---|---|
| f107 | 太阳射电流量 |
| f107a | 81 天平均太阳射电流量 |
| dst | Dst 地磁指数 |
| ap | Ap 地磁指数 |
| kp | Kp 地磁指数 |

---

## 10.2 历史记忆参数

包括：

- dst_lag_1
- dst_lag_3
- dst_lag_6
- dst_lag_12
- dst_lag_24

以及：

- ap lag
- kp lag

---

## 10.3 太阳活动历史参数

包括：

- f107_lag_24
- f107_lag_72
- f107_lag_168
- f107_lag_648

以及：

- f107a 对应 lag

---

# 11. 典型流程

```text
1. 准备 EOF 文件
2. 准备 CatBoost 模型
3. 修改 YAML 参数
4. 运行程序
5. 输出 TEC 图和 TEC 网格
```

---

# 12. 注意事项

## 12.1 当前版本完全不依赖 swindex.csv

因此：

所有模型输入参数都必须由用户手动提供。

---

## 12.2 模型输入维度必须完整

如果缺少某个 lag 参数：

模型预测可能报错。

---

# 13. 学术用途

本代码适用于：

- 全球 TEC 建模
- 电离层气候学研究
- HF 链路传播背景场生成
- MUF 预测
- AI 电离层模型研究

如用于论文，请引用相关 TemporalMemoryEOF 工作。
