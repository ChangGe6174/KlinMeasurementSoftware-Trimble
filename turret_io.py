# -*- coding: utf-8 -*-
"""托轮棱镜坐标文件的解析。"""
import re
from typing import Optional

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


UNIT_FACTOR = 1000.0
NUM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _extract_float(token: object) -> Optional[float]:
    if token is None:
        return None
    if isinstance(token, (int, float)):
        return float(token)
    text = str(token).strip()
    if not text:
        return None
    match = NUM_RE.match(text)
    if not match:
        return None
    return float(match.group(0))


def _parse_axis_labels(raw_lines: list[list[str]]) -> Optional[list[tuple[float, float, float]]]:
    if not raw_lines:
        return None
    axes: dict[str, list[float]] = {"X": [], "Y": [], "Z": []}
    for tokens in raw_lines:
        if not tokens or not any(_extract_float(token) is not None for token in tokens):
            continue
        head = tokens[0].strip().upper()
        axis = head[:1] if head[:1] in axes and (len(head) == 1 or not head[1].isdigit()) else None
        if axis is None:
            return None
        axes[axis].extend(value for value in (_extract_float(token) for token in tokens[1:]) if value is not None)

    if not all(axes.values()):
        return None
    lengths = {len(values) for values in axes.values()}
    if len(lengths) != 1:
        raise RuntimeError(
            "按 X/Y/Z 轴标签解析时，三轴数据点数不一致："
            f" X={len(axes['X'])}, Y={len(axes['Y'])}, Z={len(axes['Z'])}"
        )
    return list(zip(axes["X"], axes["Y"], axes["Z"]))


def read_prism_file(path: str) -> list[tuple[float, float, float]]:
    """读取米制棱镜坐标文件并转换为毫米。"""
    raw_lines: list[list[str]] = []
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if ext in ("xlsx", "xls"):
        if load_workbook is None:
            raise RuntimeError("读取 Excel 文件需要 openpyxl 库，请执行：pip install openpyxl")
        workbook = load_workbook(path, data_only=True, read_only=True)
        try:
            for row in workbook.active.iter_rows(values_only=True):
                tokens = ["" if cell is None else str(cell) for cell in row]
                if any(token.strip() for token in tokens):
                    raw_lines.append(tokens)
        finally:
            workbook.close()
    else:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    tokens = line.replace(",", " ").replace("\t", " ").split()
                    if tokens:
                        raw_lines.append(tokens)

    if not raw_lines:
        return []

    axis_result = _parse_axis_labels(raw_lines)
    if axis_result is not None:
        return [(x * UNIT_FACTOR, y * UNIT_FACTOR, z * UNIT_FACTOR) for x, y, z in axis_result]

    raw_rows = [
        [value for value in (_extract_float(token) for token in tokens) if value is not None]
        for tokens in raw_lines
    ]
    raw_rows = [row for row in raw_rows if row]
    if not raw_rows:
        return []

    if all(len(row) >= 3 for row in raw_rows):
        points = [(row[0], row[1], row[2]) for row in raw_rows]
    elif all(len(row) == 1 for row in raw_rows) and len(raw_rows) % 3 == 0:
        n = len(raw_rows) // 3
        values = [row[0] for row in raw_rows]
        points = list(zip(values[:n], values[n:2 * n], values[2 * n:]))
    elif any(len(row) >= 3 for row in raw_rows):
        points = [(row[0], row[1], row[2]) for row in raw_rows if len(row) >= 3]
    elif len(raw_rows) % 3 == 0:
        n = len(raw_rows) // 3
        values = [row[0] for row in raw_rows]
        points = list(zip(values[:n], values[n:2 * n], values[2 * n:]))
    else:
        raise RuntimeError(
            "无法识别文件格式：请使用轴标签矩阵、每行 x y z，或一列且总数为 3 的倍数的数字。"
        )
    return [(x * UNIT_FACTOR, y * UNIT_FACTOR, z * UNIT_FACTOR) for x, y, z in points]
