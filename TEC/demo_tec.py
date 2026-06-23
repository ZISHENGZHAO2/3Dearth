#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单时刻全球电离层 TEC 计算与绘图脚本。

功能：
  1. 只调用 TemporalMemoryEOF-CatBoost MEMORY_MODEL；
  2. 不读取 swindex.csv；
  3. 所有模型输入参数均从 YAML 文件读取；
  4. 每次运行只计算一个指定时刻 year + doy + ut_hour 的全球 TEC 图；
  5. 可输出 TEC 图像和 TEC 网格 npz 文件。

运行示例：
  python demo_memory_model_tec_single_time.py --config memory_tec_single_time_config.yaml

说明：
  YAML 中的 kp 使用真实 Kp 值，例如 3.7，不是 swindex.csv 中的 Kp*10。
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path
from typing import Any, Dict, List, Mapping

import numpy as np
import pandas as pd
import yaml
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature


# ==========================================================
# 常量设置
# ==========================================================

N_MODES = 15
N_LAT = 71
N_LON = 73

LATS = np.linspace(-87.5, 87.5, N_LAT)
LONS = np.linspace(-180, 180, N_LON)

# MEMORY_MODEL 的历史记忆项顺序必须与训练时保持一致
SHORT_LAGS = [1, 3, 6, 12, 24]      # Dst / Ap / Kp，单位：小时
SOLAR_LAGS = [24, 72, 168, 648]     # F10.7 / F10.7A，单位：小时

REQUIRED_BASE_DRIVERS = ["f107", "f107a", "dst", "ap", "kp"]


# ==========================================================
# 参数与配置读取
# ==========================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 YAML 输入参数，调用 MEMORY_MODEL 计算单时刻全球 TEC 地图。"
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="YAML 配置文件路径，例如 memory_tec_single_time_config.yaml。",
    )
    return parser.parse_args()


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"缺少必要文件: {path}")


def load_config(path: Path) -> Dict[str, Any]:
    require_file(path)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("YAML 配置文件的顶层必须是字典结构。")
    return cfg


def cfg_get(cfg: Mapping[str, Any], key: str, default: Any = None, required: bool = False) -> Any:
    if key in cfg:
        return cfg[key]
    if required:
        raise KeyError(f"YAML 中缺少必要字段: {key}")
    return default


def as_path(value: Any, key: str) -> Path:
    if value is None:
        raise KeyError(f"YAML 中缺少路径字段: {key}")
    return Path(str(value))


def validate_time(year: int, doy: int, ut_hour: int) -> None:
    if year < 1900 or year > 2200:
        raise ValueError(f"year 数值异常: {year}")
    if not 1 <= doy <= 366:
        raise ValueError(f"doy 必须在 1-366 之间，当前为: {doy}")
    if not 0 <= ut_hour <= 23:
        raise ValueError(f"ut_hour 必须在 0-23 之间，当前为: {ut_hour}")


# ==========================================================
# EOF 与模型读取
# ==========================================================

def load_eof_basis(data_dir: Path):
    eof_path = data_dir / "eof_maps.csv"
    mean_path = data_dir / "tec_mean.csv"
    require_file(eof_path)
    require_file(mean_path)

    print("正在读取 EOF 基函数与 TEC 平均场...")

    eof_flat = pd.read_csv(eof_path, header=None).values
    if eof_flat.shape[1] < N_MODES:
        raise ValueError(
            f"eof_maps.csv 至少应包含 {N_MODES} 个 EOF 模态，当前形状为 {eof_flat.shape}。"
        )

    eof_maps = np.zeros((N_LAT, N_LON, N_MODES), dtype=float)
    for k in range(N_MODES):
        eof_maps[:, :, k] = eof_flat[:, k].reshape(N_LAT, N_LON, order="F")

    tec_mean = pd.read_csv(mean_path, header=None).values
    if tec_mean.shape != (N_LAT, N_LON):
        raise ValueError(f"tec_mean.csv 形状应为 {(N_LAT, N_LON)}，当前为 {tec_mean.shape}。")

    # 原始文件为 north-to-south；翻转为 south-to-north，以匹配 LATS。
    eof_maps = np.flip(eof_maps, axis=0)
    tec_mean = np.flip(tec_mean, axis=0)

    return eof_maps, tec_mean


def load_memory_model(model_path: Path):
    require_file(model_path)
    print(f"正在读取 MEMORY_MODEL: {model_path}")
    with open(model_path, "rb") as f:
        return pickle.load(f)


# ==========================================================
# 特征构建
# ==========================================================

def require_number(mapping: Mapping[str, Any], key: str, parent: str) -> float:
    if key not in mapping:
        raise KeyError(f"缺少必要参数: {parent}.{key}")
    try:
        return float(mapping[key])
    except Exception as exc:
        raise TypeError(f"{parent}.{key} 必须是数值，当前为 {mapping[key]!r}") from exc


def lag_value(
    lag_cfg: Mapping[str, Any] | None,
    var_name: str,
    lag: int,
    fallback: float,
    cfg_name: str,
) -> float:
    """
    从 YAML 中读取滞后项。

    支持格式：
      memory_lags:
        dst:
          1: -12.0
          3: -15.0

    若某个滞后项未填写，则默认使用当前时刻对应变量值。
    """
    if not lag_cfg:
        return float(fallback)

    var_cfg = lag_cfg.get(var_name, {})
    if var_cfg is None:
        return float(fallback)
    if not isinstance(var_cfg, Mapping):
        raise TypeError(f"{cfg_name}.{var_name} 必须是 lag_hour: value 的映射。")

    value = var_cfg.get(lag, var_cfg.get(str(lag), fallback))
    try:
        return float(value)
    except Exception as exc:
        raise TypeError(f"{cfg_name}.{var_name}.{lag} 必须是数值，当前为 {value!r}") from exc


def build_single_feature_vector(cfg: Mapping[str, Any]) -> tuple[int, int, int, np.ndarray]:
    year = int(cfg_get(cfg, "year", required=True))
    doy = int(cfg_get(cfg, "doy", required=True))
    ut_hour = int(cfg_get(cfg, "ut_hour", required=True))
    validate_time(year, doy, ut_hour)

    drivers = cfg_get(cfg, "drivers", required=True)
    if not isinstance(drivers, Mapping):
        raise TypeError("drivers 必须是 YAML 字典。")

    memory_lags = cfg_get(cfg, "memory_lags", {})
    solar_lags = cfg_get(cfg, "solar_lags", {})

    if memory_lags is not None and not isinstance(memory_lags, Mapping):
        raise TypeError("memory_lags 必须是 YAML 字典。")
    if solar_lags is not None and not isinstance(solar_lags, Mapping):
        raise TypeError("solar_lags 必须是 YAML 字典。")

    for name in REQUIRED_BASE_DRIVERS:
        if name not in drivers:
            raise KeyError(f"drivers 中缺少必要参数: {name}")

    f107 = require_number(drivers, "f107", "drivers")
    f107a = require_number(drivers, "f107a", "drivers")
    dst = require_number(drivers, "dst", "drivers")
    ap = require_number(drivers, "ap", "drivers")
    kp = require_number(drivers, "kp", "drivers")

    doy_sin = np.sin(2.0 * np.pi * doy / 366.0)
    doy_cos = np.cos(2.0 * np.pi * doy / 366.0)
    hour_sin = np.sin(2.0 * np.pi * ut_hour / 24.0)
    hour_cos = np.cos(2.0 * np.pi * ut_hour / 24.0)

    features: List[float] = [
        doy_sin,
        doy_cos,
        hour_sin,
        hour_cos,
        f107,
        f107a,
        dst,
        ap,
        kp,
    ]

    # Dst / Ap / Kp 短期历史记忆项
    for lag in SHORT_LAGS:
        features.extend([
            lag_value(memory_lags, "dst", lag, dst, "memory_lags"),
            lag_value(memory_lags, "ap", lag, ap, "memory_lags"),
            lag_value(memory_lags, "kp", lag, kp, "memory_lags"),
        ])

    # F10.7 / F10.7A 长期历史记忆项
    for lag in SOLAR_LAGS:
        features.extend([
            lag_value(solar_lags, "f107", lag, f107, "solar_lags"),
            lag_value(solar_lags, "f107a", lag, f107a, "solar_lags"),
        ])

    x = np.asarray(features, dtype=float).reshape(1, -1)
    expected = 9 + 3 * len(SHORT_LAGS) + 2 * len(SOLAR_LAGS)
    if x.shape[1] != expected:
        raise RuntimeError(f"特征数量应为 {expected}，当前为 {x.shape[1]}")

    print(f"已构建单时刻 MEMORY_MODEL 输入特征: X.shape={x.shape}")
    return year, doy, ut_hour, x


def feature_names() -> List[str]:
    names = [
        "doy_sin", "doy_cos", "hour_sin", "hour_cos",
        "f107", "f107a", "dst", "ap", "kp",
    ]
    for lag in SHORT_LAGS:
        names.extend([f"dst_lag_{lag}h", f"ap_lag_{lag}h", f"kp_lag_{lag}h"])
    for lag in SOLAR_LAGS:
        names.extend([f"f107_lag_{lag}h", f"f107a_lag_{lag}h"])
    return names


# ==========================================================
# TEC 重建与绘图
# ==========================================================

def reconstruct_tec(pc, eof_maps, tec_mean) -> np.ndarray:
    pc = np.asarray(pc, dtype=float).ravel()
    if pc.size != N_MODES:
        raise ValueError(f"模型输出 PC 数量应为 {N_MODES}，当前为 {pc.size}。")
    return tec_mean + np.tensordot(eof_maps, pc, axes=([2], [0]))


def predict_single_tec_map(model, x_memory: np.ndarray, eof_maps, tec_mean) -> np.ndarray:
    pc_pred = model.predict(x_memory)
    pc_pred = np.asarray(pc_pred)
    if pc_pred.ndim == 2:
        pc_pred = pc_pred[0]
    return reconstruct_tec(pc_pred, eof_maps, tec_mean)


def plot_single_tec_map(
    tec_map: np.ndarray,
    year: int,
    doy: int,
    ut_hour: int,
    out_fig: Path,
    vmin: float,
    vmax: float,
    cmap: str,
    dpi: int,
    no_borders: bool,
    title: str | None,
) -> None:
    fig = plt.figure(figsize=(11, 5.6))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())

    im = ax.pcolormesh(
        LONS,
        LATS,
        tec_map,
        transform=ccrs.PlateCarree(),
        cmap=cmap,
        shading="auto",
        vmin=vmin,
        vmax=vmax,
    )

    ax.coastlines(linewidth=0.6)
    if not no_borders:
        ax.add_feature(cfeature.BORDERS, linewidth=0.25)
    ax.set_global()

    xticks = [-180, -90, 0, 90, 180]
    yticks = [-60, -30, 0, 30, 60]
    ax.set_xticks(xticks, crs=ccrs.PlateCarree())
    ax.set_yticks(yticks, crs=ccrs.PlateCarree())
    ax.set_xticklabels([r"180°", r"90°W", r"0°", r"90°E", r"180°"], fontsize=10)
    ax.set_yticklabels([r"60°S", r"30°S", r"0°", r"30°N", r"60°N"], fontsize=10)
    ax.tick_params(axis="both", which="major", labelsize=10, pad=2, length=3)

    if title is None or str(title).strip() == "":
        title = f"TemporalMemoryEOF-CatBoost Global TEC | {year}, DOY={doy:03d}, {ut_hour:02d}:00 UT"
    ax.set_title(title, fontsize=14, pad=10)

    cb = fig.colorbar(im, ax=ax, orientation="horizontal", pad=0.08, fraction=0.055)
    cb.set_label("TECU", fontsize=13)
    cb.ax.tick_params(labelsize=11)

    out_fig.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_fig, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"已保存 TEC 图像: {out_fig}")


# ==========================================================
# 主程序
# ==========================================================

def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    data_dir = as_path(cfg_get(cfg, "data_dir", "./uploads"), "data_dir")
    memory_model_path = as_path(
        cfg_get(
            cfg,
            "memory_model_path",
            "./outputs/TemporalMemoryEOF_climatology/saved_models/TemporalMemoryEOF-CatBoost.pkl",
        ),
        "memory_model_path",
    )

    year, doy, ut_hour, x_memory = build_single_feature_vector(cfg)

    output_cfg = cfg_get(cfg, "output", {}) or {}
    if not isinstance(output_cfg, Mapping):
        raise TypeError("output 必须是 YAML 字典。")

    default_fig = f"fig_memory_tec_{year}{doy:03d}_{ut_hour:02d}UT.svg"
    out_fig = Path(str(output_cfg.get("figure", default_fig)))

    npz_value = output_cfg.get("npz", f"memory_tec_{year}{doy:03d}_{ut_hour:02d}UT.npz")
    save_npz = None if npz_value in (None, "", False) else Path(str(npz_value))

    plot_cfg = cfg_get(cfg, "plot", {}) or {}
    if not isinstance(plot_cfg, Mapping):
        raise TypeError("plot 必须是 YAML 字典。")

    vmin = float(plot_cfg.get("vmin", 0.0))
    vmax = float(plot_cfg.get("vmax", 100.0))
    cmap = str(plot_cfg.get("cmap", "jet"))
    dpi = int(plot_cfg.get("dpi", 300))
    no_borders = bool(plot_cfg.get("no_borders", False))
    title = plot_cfg.get("title", None)

    eof_maps, tec_mean = load_eof_basis(data_dir)
    memory_model = load_memory_model(memory_model_path)

    tec_map = predict_single_tec_map(memory_model, x_memory, eof_maps, tec_mean)

    plot_single_tec_map(
        tec_map=tec_map,
        year=year,
        doy=doy,
        ut_hour=ut_hour,
        out_fig=out_fig,
        vmin=vmin,
        vmax=vmax,
        cmap=cmap,
        dpi=dpi,
        no_borders=no_borders,
        title=title,
    )

    if save_npz is not None:
        save_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            save_npz,
            tec=tec_map,
            lats=LATS,
            lons=LONS,
            year=year,
            doy=doy,
            ut_hour=ut_hour,
            feature_vector=x_memory,
            feature_order=np.asarray(feature_names(), dtype=object),
        )
        print(f"已保存 TEC 网格数据: {save_npz}")


if __name__ == "__main__":
    main()
