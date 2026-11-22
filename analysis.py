# -*- coding: utf-8 -*-
"""回转窑中心线分析的纯数据逻辑。

本模块不依赖 Tkinter，便于单独测试或在其他界面中复用。
"""
import os
from typing import Optional

import numpy as np


def read_section_points(file_path: str) -> np.ndarray:
    """读取截面点云，统一换算为 mm 后返回 N x 3 的 XYZ 数组。"""
    points, _ = read_section_points_with_rows(file_path)
    return points


def read_section_points_with_rows(file_path: str) -> tuple[np.ndarray, np.ndarray]:
    """读取截面点云，并返回每个有效点对应的原始表格行号。"""
    base_name = os.path.basename(file_path)
    if base_name.startswith("~$"):
        raise ValueError(f"Excel 临时锁定文件不是有效数据文件: {base_name}")

    try:
        import pandas as pd
    except ImportError as exc:
        raise ValueError("读取截面文件需要安装 pandas") from exc
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".xlsx", ".xls"}:
        try:
            # 不使用默认表头逻辑：
            # 实际数据文件可能没有表头，也可能首行就是数值。
            # 保留所有行后，再通过数值转换和缺失值清理保留有效数据。
            df = pd.read_excel(file_path, header=None)
        except ImportError as exc:
            raise ValueError("读取 Excel 文件需要安装对应引擎（xlsx 通常需要 openpyxl）") from exc
    elif ext == ".csv":
        df = pd.read_csv(file_path, header=None)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

    if df.shape[1] < 3:
        raise ValueError("文件列数不足，至少需要包含 XYZ 三列")

    data = df.iloc[:, :3].copy()
    data.columns = ["X", "Y", "Z"]
    numeric_data = data.apply(pd.to_numeric, errors="coerce")
    valid_mask = numeric_data.notna().all(axis=1)
    numeric_data = numeric_data.loc[valid_mask]
    row_numbers = np.asarray(valid_mask.index[valid_mask], dtype=int) + 1

    return numeric_data.to_numpy(dtype=float) * 1000.0, row_numbers


def fit_circle_2d(x: np.ndarray, z: np.ndarray) -> tuple[float, float, float]:
    """二维最小二乘拟合圆，返回 (center_x, center_z, radius)。"""
    if x.size != z.size or x.size < 3:
        raise ValueError("拟合圆至少需要 3 个对应的二维点")
    lhs = np.column_stack([x, z, np.ones_like(x)])
    rhs = x ** 2 + z ** 2
    a, b, c = np.linalg.lstsq(lhs, rhs, rcond=None)[0]

    center_x = a / 2.0
    center_z = b / 2.0
    radius_squared = c + center_x ** 2 + center_z ** 2
    if radius_squared < -1e-9:
        raise ValueError("拟合结果无效：半径平方为负")
    radius = float(np.sqrt(max(radius_squared, 0.0)))
    return float(center_x), float(center_z), radius


def fit_section_center_with_axis_projection(
    points_xyz: np.ndarray,
    tan_slope: float,
    projection_y: Optional[float] = None,
) -> tuple[float, float, float, np.ndarray]:
    """将点正交投影到轴线垂直截面后拟合圆。"""
    x2d, z2d, origin, u, v = project_points_to_axis_section(
        points_xyz, tan_slope, projection_y
    )
    cu, cv, radius = fit_circle_2d(x2d, z2d)
    center_3d = origin + cu * u + cv * v
    return float(center_3d[0]), float(center_3d[2]), radius, center_3d


def project_points_to_axis_section(
    points_xyz: np.ndarray,
    tan_slope: float,
    projection_y: Optional[float] = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """将点投影到轴线垂直截面，返回二维坐标及其三维基。"""
    if points_xyz.ndim != 2 or points_xyz.shape[1] != 3:
        raise ValueError("点云必须是 N x 3 数组")
    axis = np.array([0.0, 1.0, tan_slope], dtype=float)
    axis_norm = np.linalg.norm(axis)
    if axis_norm < 1e-12:
        raise ValueError("轴线方向无效，请检查坡度 tan 值")
    axis_unit = axis / axis_norm

    origin = points_xyz.mean(axis=0)
    if projection_y is not None:
        origin = origin + (projection_y - origin[1]) * axis
    vec = points_xyz - origin
    proj = points_xyz - np.outer(vec @ axis_unit, axis_unit)

    u = np.array([1.0, 0.0, 0.0], dtype=float)
    # Keep the section's vertical coordinate aligned with global +Z.
    # cross(axis, u) points toward -Z and makes the plot appear vertically mirrored.
    v = np.cross(u, axis_unit)
    v_norm = np.linalg.norm(v)
    if v_norm < 1e-12:
        raise ValueError("截面基向量构造失败")
    v = v / v_norm

    rel = proj - origin
    x2d = rel @ u
    z2d = rel @ v
    return x2d, z2d, origin, u, v


def deviation_at_y(
    c1: dict[str, float],
    c2: dict[str, float],
    c3: dict[str, float],
) -> dict[str, float]:
    """计算在 y2 处，c2 相对 c1-c3 连线的 X/Z 偏差。"""
    y1, y2, y3 = c1["y"], c2["y"], c3["y"]
    if abs(y3 - y1) < 1e-12:
        raise ValueError("第1与第3截面的 Y 坐标不能相同，无法建立沿 Y 的连线插值")

    t = (y2 - y1) / (y3 - y1)
    x_on_line = c1["x"] + t * (c3["x"] - c1["x"])
    z_on_line = c1["z"] + t * (c3["z"] - c1["z"])

    dx = c2["x"] - x_on_line
    dz = c2["z"] - z_on_line
    return {
        "x_line": x_on_line,
        "z_line": z_on_line,
        "dx": dx,
        "dz": dz,
        "abs_dx": abs(dx),
        "abs_dz": abs(dz),
    }
