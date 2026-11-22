# -*- coding: utf-8 -*-
"""
回转窑中心线测量系统 - 整合版
  - 主界面: 一档、二档、三档圆心共线度分析（中心线）
  - 子窗口: 托轮位置设置（由 turret_position 模块提供）

依赖: pip install numpy pandas matplotlib
      可选: pip install openpyxl   (读取 .xlsx / 导出 .xlsx)
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import pandas as pd
from analysis import (
    deviation_at_y,
    fit_circle_2d,
    fit_section_center_with_axis_projection,
    project_points_to_axis_section,
    read_section_points_with_rows,
)
from turret_position import TurretPositionWindow
from txt2xlsx import convert_selected_files
from serial_acquisition import SerialAcquisitionWindow

import matplotlib
matplotlib.use("TkAgg")
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    from openpyxl import load_workbook
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


class CircleCenterApp:
    """主界面: 一档、二档、三档圆心共线度分析（中心线）。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("回转窑中心线（天宝全站仪）测量系统")
        self.root.geometry("1000x760")

        self.file_vars = [tk.StringVar() for _ in range(3)]
        self.y_vars = [tk.StringVar(value="0") for _ in range(3)]
        self.y_user_edited = [False for _ in range(3)]
        self.tan_var = tk.StringVar(value="0")
        self.radius_correction_var = tk.StringVar(value="0")
        self.last_result_data = None

        # 托轮位置窗口（保持单实例，重复点击时 lift 到前台）
        self.turret_window = None
        self.serial_acquisition_window = None

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            frame,
            text="一档、二档、三档圆心拟合与共线偏差分析",
            font=("Microsoft YaHei UI", 13, "bold"),
        )
        title.pack(anchor="w", pady=(0, 10))

        module_row = tk.Frame(frame)
        module_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            module_row,
            text="独立功能:",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            module_row,
            text="转换txt文件为表格",
            command=self._convert_txt_files,
            bg="#D9EAF7",
            activebackground="#B8D8F0",
            relief=tk.RAISED,
            padx=8,
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            module_row,
            text="打开托轮位置模块",
            command=self._open_turret_window,
            bg="#DCEFD8",
            activebackground="#BFE3B8",
            relief=tk.RAISED,
            padx=8,
        ).pack(side=tk.LEFT)
        tk.Button(
            module_row,
            text="串口数据采集",
            command=self._open_serial_acquisition,
            bg="#F5E6C8",
            activebackground="#E8CFA0",
            relief=tk.RAISED,
            padx=8,
        ).pack(side=tk.LEFT, padx=(8, 0))

        file_box = ttk.LabelFrame(
            frame,
            text="1) 选择一档、二档、三档数据文件（每档可多选，支持 xlsx/xls/csv）",
            padding=10,
        )
        file_box.pack(fill=tk.X, pady=6)
        for i in range(3):
            row = ttk.Frame(file_box)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"{i+1}档文件:", width=12).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=self.file_vars[i]).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=6
            )
            ttk.Button(row, text="添加", command=lambda idx=i: self._add_files(idx)).pack(side=tk.LEFT)
            ttk.Button(row, text="清空", command=lambda idx=i: self._clear_files(idx)).pack(
                side=tk.LEFT, padx=(6, 0)
            )

        param_box = ttk.LabelFrame(frame, text="2) 输入参数", padding=10)
        param_box.pack(fill=tk.X, pady=6)

        y_row = ttk.Frame(param_box)
        y_row.pack(fill=tk.X, pady=4)
        for i in range(3):
            ttk.Label(y_row, text=f"{i+1}档圆心Y(mm):").pack(side=tk.LEFT)
            y_entry = ttk.Entry(y_row, textvariable=self.y_vars[i], width=10)
            y_entry.pack(side=tk.LEFT, padx=(4, 12))
            y_entry.bind("<KeyRelease>", lambda event, idx=i: self._handle_y_edit(event, idx))
            y_entry.bind("<<Paste>>", lambda event, idx=i: self._handle_y_edit(event, idx))
            y_entry.bind("<<Cut>>", lambda event, idx=i: self._handle_y_edit(event, idx))

        slope_row = ttk.Frame(param_box)
        slope_row.pack(fill=tk.X, pady=4)
        ttk.Label(slope_row, text="坡度角 tan 值:").pack(side=tk.LEFT)
        ttk.Entry(slope_row, textvariable=self.tan_var, width=12).pack(side=tk.LEFT, padx=(4, 18))
        ttk.Label(slope_row, text="轴线方向: +Y 且沿 +Z 爬升").pack(side=tk.LEFT)

        corr_row = ttk.Frame(param_box)
        corr_row.pack(fill=tk.X, pady=4)
        ttk.Label(corr_row, text="半径修正值(mm，测量偏大时输入正值)(滚轮半径):").pack(side=tk.LEFT)
        ttk.Entry(corr_row, textvariable=self.radius_correction_var, width=12).pack(side=tk.LEFT, padx=6)

        tip = ttk.Label(
            param_box,
            text="说明: Y值默认自动取该档全部点的平均值并回填；主动输入后按输入值投影。长度量均按 mm 处理。",
            foreground="#585454",
        )
        tip.pack(anchor="w", pady=(4, 0))

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, pady=10)
        ttk.Button(action_row, text="开始分析", command=self.run_analysis).pack(side=tk.LEFT)
        ttk.Button(action_row, text="清空结果", command=self._clear_result).pack(side=tk.LEFT, padx=8)
        ttk.Button(action_row, text="导出结果到 Excel/CSV", command=self.export_results).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(action_row, text="查看分析图形", command=self.show_analysis_plots).pack(
            side=tk.LEFT, padx=8
        )

        result_box = ttk.LabelFrame(frame, text="3) 分析结果", padding=10)
        result_box.pack(fill=tk.BOTH, expand=True, pady=6)
        self.result_text = tk.Text(result_box, wrap=tk.WORD, font=("Consolas", 10))
        self.result_text.pack(fill=tk.BOTH, expand=True)

    def _open_turret_window(self) -> None:
        """打开托轮位置设置子窗口；若已存在则 lift 到前台。"""
        if self.turret_window is not None and self.turret_window.winfo_exists():
            self.turret_window.lift()
            self.turret_window.focus_set()
            return
        self.turret_window = TurretPositionWindow(self.root)

    def _open_serial_acquisition(self) -> None:
        """打开串口助手与数据采集子窗口。"""
        if self.serial_acquisition_window is not None and self.serial_acquisition_window.winfo_exists():
            self.serial_acquisition_window.lift()
            self.serial_acquisition_window.focus_set()
            return
        self.serial_acquisition_window = SerialAcquisitionWindow(self.root)

    def _convert_txt_files(self) -> None:
        """打开 txt 转表格功能。"""
        convert_selected_files(self.root)

    def _add_files(self, idx: int) -> None:
        paths = filedialog.askopenfilenames(
            title=f"选择{idx+1}档数据文件",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("All Files", "*.*")],
        )
        if paths:
            existing_paths = self._get_file_paths(idx)
            all_paths = existing_paths + [path for path in paths if path not in existing_paths]
            self.file_vars[idx].set("; ".join(all_paths))

    def _clear_files(self, idx: int) -> None:
        self.file_vars[idx].set("")

    def _handle_y_edit(self, event: tk.Event, idx: int) -> None:
        if event.widget is not None:
            self.y_user_edited[idx] = True

    def _get_file_paths(self, idx: int) -> list[str]:
        value = self.file_vars[idx].get().strip()
        if not value:
            return []
        paths = []
        for path in value.replace("\n", ";").split(";"):
            path = path.strip()
            if not path:
                continue
            if os.path.basename(path).startswith("~$"):
                continue
            if path not in paths:
                paths.append(path)
        return paths

    def _clear_result(self, clear_data: bool = True) -> None:
        self.result_text.delete("1.0", tk.END)
        if clear_data:
            self.last_result_data = None

    def _append_result(self, text: str) -> None:
        self.result_text.insert(tk.END, text + "\n")
        self.result_text.see(tk.END)

    def show_analysis_plots(self) -> None:
        """分别显示一档、二档、三档拟合图和两个圆心投影图。"""
        if self.last_result_data is None or "sections" not in self.last_result_data:
            messagebox.showwarning("无可绘制数据", "请先点击【开始分析】生成结果")
            return

        data = self.last_result_data

        for index, section in enumerate(data["sections"]):
            figure = Figure(figsize=(8, 7), dpi=100)
            ax = figure.add_subplot(111)
            x_values = section["x2d"]
            z_values = section["z2d"]
            center_x, center_z, radius = section["center_2d"]
            ax.scatter(x_values, z_values, s=12, alpha=0.25, color="0.55", label="实际投影点")
            angles = np.linspace(0, 2 * np.pi, 361)
            ax.plot(
                center_x + radius * np.cos(angles),
                center_z + radius * np.sin(angles),
                color="tab:red",
                label=f"拟合圆 R={radius:.2f} mm",
            )
            ax.scatter([center_x], [center_z], color="black", marker="x", label="拟合圆心")

            point_distances = np.hypot(x_values - center_x, z_values - center_z)
            radial_deviations = point_distances - radius
            max_absolute_deviation = float(np.max(np.abs(radial_deviations)))
            exaggeration = 1.0
            if max_absolute_deviation > 1e-12:
                exaggeration = float(np.clip(
                    0.20 * radius / max_absolute_deviation,
                    10.0,
                    1000.0,
                ))

            visual_x = np.empty_like(x_values)
            visual_z = np.empty_like(z_values)
            for point_index, (x_value, z_value) in enumerate(zip(x_values, z_values)):
                dx = x_value - center_x
                dz = z_value - center_z
                distance = float(np.hypot(dx, dz))
                if distance > 1e-12:
                    visual_radius = radius + exaggeration * (
                        distance - radius
                    )
                    visual_radius = max(visual_radius, 0.0)
                    visual_x[point_index] = center_x + dx / distance * visual_radius
                    visual_z[point_index] = center_z + dz / distance * visual_radius
                else:
                    visual_x[point_index] = center_x
                    visual_z[point_index] = center_z

            file_palette = [
                "tab:blue", "tab:orange", "tab:green", "tab:red",
                "tab:purple", "tab:brown", "tab:pink", "tab:gray",
                "tab:olive", "tab:cyan",
            ]
            file_indices = {}
            sources = section.get("point_sources", [])
            for point_index, (visual_x_value, visual_z_value) in enumerate(
                zip(visual_x, visual_z)
            ):
                source = sources[point_index] if point_index < len(sources) else {
                    "file": "未知文件", "row": point_index + 1
                }
                file_name = source["file"]
                if file_name not in file_indices:
                    file_indices[file_name] = len(file_indices)
                color = file_palette[file_indices[file_name] % len(file_palette)]
                ax.scatter(
                    [visual_x_value],
                    [visual_z_value],
                    s=42,
                    color=color,
                    edgecolors="black",
                    linewidths=0.4,
                )
                ax.plot(
                    [x_values[point_index], visual_x_value],
                    [z_values[point_index], visual_z_value],
                    color=color,
                    alpha=0.35,
                    linewidth=0.7,
                )
                ax.annotate(
                    str(source["row"]),
                    (visual_x_value, visual_z_value),
                    xytext=(3, 3),
                    textcoords="offset points",
                    fontsize=7,
                    color=color,
                    weight="bold",
                )

            for file_name, file_index in file_indices.items():
                color = file_palette[file_index % len(file_palette)]
                ax.scatter([], [], color=color, s=20, label=os.path.basename(file_name))
            ax.plot([], [], "k--", label=f"径向偏离放大 {exaggeration:.1f} 倍")
            ax.set_title(f"{index + 1}档：投影点与拟合圆")
            ax.set_xlabel("档位横向坐标 (mm)")
            ax.set_ylabel("档位垂直坐标 (mm)")
            ax.set_aspect("equal", adjustable="datalim")
            ax.grid(True, linestyle="--", alpha=0.35)
            ax.legend(fontsize=8)
            self._show_plot_window(f"{index + 1}档拟合圆", figure)

        centers = data["centers"]
        for horizontal_key, title, xlabel in (
            ("x", "水平面 XY：一档、二档、三档圆投影椭圆及水平直径", "X (mm)"),
            ("z", "垂直面 YZ：一档、二档、三档圆投影直径及圆心连线", "Z (mm)"),
        ):
            figure = Figure(figsize=(8, 7), dpi=100)
            ax = figure.add_subplot(111)
            self._plot_center_plane(
                ax,
                centers,
                data["raw_radii"],
                horizontal_key,
                "y",
                title,
                xlabel,
                "Y (mm)",
                data["tan_slope"],
            )
            self._show_plot_window(title, figure)

    def _show_plot_window(self, title: str, figure: Figure) -> None:
        """在独立窗口中显示一张分析图。"""
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("900x760")
        canvas = FigureCanvasTkAgg(figure, master=window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    @staticmethod
    def _plot_center_plane(
        ax, centers, radii, horizontal_key, vertical_key, title, xlabel, ylabel, tan_slope
    ):
        """绘制一档、二档、三档截面圆在水平面或垂直面的投影及直径。"""
        horizontal = np.array([center[horizontal_key] for center in centers], dtype=float)
        vertical = np.array([center[vertical_key] for center in centers], dtype=float)
        colors = ["tab:blue", "tab:orange", "tab:green"]
        for index, (x_value, y_value, radius) in enumerate(
            zip(horizontal, vertical, radii)
        ):
            if horizontal_key == "x":
                axis_norm = float(np.sqrt(1.0 + tan_slope * tan_slope))
                projected_y_radius = radius * abs(tan_slope) / axis_norm
                ax.add_patch(
                    matplotlib.patches.Ellipse(
                        (x_value, y_value),
                        width=2.0 * radius,
                        height=2.0 * projected_y_radius,
                        fill=False,
                        edgecolor=colors[index],
                        alpha=0.55,
                        linestyle=":",
                        label=f"{index + 1}档拟合圆水平投影椭圆",
                    )
                )
                ax.plot(
                    [x_value - radius, x_value + radius],
                    [y_value, y_value],
                    color=colors[index],
                    linewidth=1.8,
                    label=f"{index + 1}档水平直径",
                )
                ax.scatter(
                    [x_value - radius, x_value, x_value + radius],
                    [y_value, y_value, y_value],
                    color=colors[index],
                    s=[28, 38, 28],
                    zorder=4,
                )
            else:
                axis_norm = float(np.sqrt(1.0 + tan_slope * tan_slope))
                dy = -tan_slope / axis_norm
                dz = 1.0 / axis_norm
                start_y = y_value - radius * dy
                end_y = y_value + radius * dy
                start_z = x_value - radius * dz
                end_z = x_value + radius * dz
                ax.plot(
                    [start_z, end_z],
                    [start_y, end_y],
                    color=colors[index],
                    linewidth=1.8,
                    label=f"{index + 1}档垂直投影直径",
                )
                ax.scatter(
                    [start_z, x_value, end_z],
                    [start_y, y_value, end_y],
                    color=colors[index],
                    s=[28, 38, 28],
                    zorder=4,
                )
        ax.plot(horizontal[[0, 2]], vertical[[0, 2]], "k--", label="一档-三档圆心连线")
        ax.plot(horizontal, vertical, "o", color="tab:blue")
        for index, (x_value, y_value) in enumerate(zip(horizontal, vertical), start=1):
            ax.annotate(f"{index}档", (x_value, y_value), xytext=(5, 5), textcoords="offset points")

        dx = horizontal[2] - horizontal[0]
        dy = vertical[2] - vertical[0]
        denominator = dx * dx + dy * dy
        if denominator > 1e-12:
            t = ((horizontal[1] - horizontal[0]) * dx + (vertical[1] - vertical[0]) * dy) / denominator
            foot_x = horizontal[0] + t * dx
            foot_y = vertical[0] + t * dy
            distance = float(np.hypot(horizontal[1] - foot_x, vertical[1] - foot_y))
            ax.plot([horizontal[1], foot_x], [vertical[1], foot_y], color="tab:red",
                    linestyle=":", label=f"实际偏差={distance:.2f} mm")
            ax.scatter([foot_x], [foot_y], color="tab:red", s=25)
            ax.annotate(f"d={distance:.2f} mm", (foot_x, foot_y), xytext=(5, -15),
                        textcoords="offset points", color="tab:red")

            # Keep the measured point unchanged, but enlarge the deviation vector
            # in the diagram so its direction remains visible at normal scale.
            line_length = float(np.hypot(dx, dy))
            if distance > 1e-12 and line_length > 1e-12:
                exaggeration = min(1000, max(1.0, 0.8 * line_length / distance))
                visual_x = foot_x + exaggeration * (horizontal[1] - foot_x)
                visual_y = foot_y + exaggeration * (vertical[1] - foot_y)
                ax.plot(
                    [foot_x, visual_x],
                    [foot_y, visual_y],
                    color="tab:red",
                    linewidth=1.5,
                    linestyle="--",
                    marker=">",
                    markevery=[-1],
                    label=f"偏差方向（放大{exaggeration:.1f}倍）",
                )
                ax.scatter(
                    [visual_x],
                    [visual_y],
                    facecolors="none",
                    edgecolors="tab:red",
                    marker="o",
                    s=45,
                )
                ax.annotate(
                    "放大位置（非实际坐标）",
                    (visual_x, visual_y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    color="tab:red",
                    fontsize=8,
                )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, linestyle="--", alpha=0.35)
        ax.legend(fontsize=8)
        ax.set_aspect("equal", adjustable="datalim")

    def export_results(self) -> None:
        if self.last_result_data is None:
            # 修复：内层使用【】，避免英文双引号嵌套破坏字符串
            messagebox.showwarning("无可导出数据", "请先点击【开始分析】生成结果")
            return

        save_path = filedialog.asksaveasfilename(
            title="导出分析结果",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not save_path:
            return

        ext = os.path.splitext(save_path)[1].lower()
        data = self.last_result_data

        export_rows = []
        for i, c in enumerate(data["centers"], start=1):
            valid_point_count = data.get("valid_point_counts", [np.nan] * len(data["centers"]))[i - 1]
            export_rows.append(
                {
                    "档位序号": i,
                    "有效数据点数量": valid_point_count,
                    "圆心X(mm)": c["x"],
                    "圆心Y(mm)": c["y"],
                    "圆心Z(mm)": c["z"],
                    "拟合半径(mm)": data["raw_radii"][i - 1],
                    "修正后半径(mm)": data["corrected_radii"][i - 1],
                    "二档相对一档-三档连线X偏差(mm)": data["deviation"]["dx"] if i == 2 else np.nan,
                    "二档相对一档-三档连线Z偏差(mm)": data["deviation"]["dz"] if i == 2 else np.nan,
                }
            )
        export_df = pd.DataFrame(export_rows)
        numeric_cols = export_df.select_dtypes(include=[np.number]).columns
        export_df[numeric_cols] = export_df[numeric_cols].round(3)

        try:
            if ext == ".csv":
                export_df.to_csv(save_path, index=False, encoding="utf-8-sig")
            else:
                if not HAS_OPENPYXL:
                    raise RuntimeError("导出 Excel 文件需要 openpyxl 库，请执行：pip install openpyxl")
                with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
                    export_df.to_excel(writer, sheet_name="results", index=False)

            messagebox.showinfo("导出成功", f"结果已导出到:\n{save_path}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def run_analysis(self) -> None:
        try:
            file_paths = [self._get_file_paths(i) for i in range(3)]
            if not all(file_paths):
                raise ValueError("请先为一档、二档、三档选择数据文件")

            section_points = []
            section_point_sources = []
            average_y_values = []
            insufficient_sections = []
            for i, paths in enumerate(file_paths, start=1):
                file_points = []
                point_sources = []
                for path in paths:
                    points, row_numbers = read_section_points_with_rows(path)
                    file_points.append(points)
                    point_sources.extend(
                        {"file": path, "row": int(row_number)}
                        for row_number in row_numbers
                    )
                points = np.vstack(file_points)
                section_point_sources.append(point_sources)
                valid_count = int(points.shape[0])
                if valid_count < 3:
                    insufficient_sections.append(f"{i}档有效数据点共 {valid_count} 个")
                section_points.append(points)
                if valid_count == 0:
                    average_y_values.append(float("nan"))
                    continue
                average_y_values.append(float(points[:, 1].mean()))
            if insufficient_sections:
                raise ValueError(
                    "有效数据点不足 3 个，无法拟合圆。\n"
                    "判定依据为每个档位所有已选文件合计有效点数：\n"
                    + "；".join(insufficient_sections)
                )

            y1, y2, y3 = average_y_values
            if y1 < y2 < y3:
                expected_tan_sign = "正"
            elif y1 > y2 > y3:
                expected_tan_sign = "负"
            else:
                raise ValueError(
                    "三档平均Y坐标不是严格单调顺序，无法判断坡度值 tan 的正负。\n"
                    f"当前平均Y：一档={y1:.3f}，二档={y2:.3f}，三档={y3:.3f}\n"
                    "请检查三档数据文件及坐标原点设置。"
                )

            tan_text = self.tan_var.get().strip()
            if not tan_text:
                raise ValueError(
                    "坡度值 tan 未输入，无法开始分析。\n\n"
                    f"根据平均Y坐标顺序，当前应输入{expected_tan_sign}值。"
                )
            tan_slope = float(tan_text)
            if abs(tan_slope) < 1e-12:
                raise ValueError(
                    "坡度值 tan 不能为 0。\n\n"
                    f"根据平均Y坐标顺序，当前应输入{expected_tan_sign}值。"
                )
            if (expected_tan_sign == "正" and tan_slope < 0) or (
                expected_tan_sign == "负" and tan_slope > 0
            ):
                raise ValueError(
                    "坡度值 tan 正负号错误，已停止分析！\n\n"
                    f"三档平均Y坐标：一档={y1:.3f}，二档={y2:.3f}，三档={y3:.3f}\n"
                    f"按当前坐标约定，坡度值 tan 应输入{expected_tan_sign}值，"
                    f"当前输入为 {tan_slope:g}。"
                )

            radius_correction = float(self.radius_correction_var.get().strip())

            raw_centers = []
            raw_radii = []
            section_results = []
            valid_point_counts = []
            for i, pts in enumerate(section_points):
                valid_point_counts.append(int(pts.shape[0]))
                if self.y_user_edited[i]:
                    y_value = float(self.y_vars[i].get().strip())
                else:
                    y_value = float(pts[:, 1].mean())
                    self.y_vars[i].set(f"{y_value:g}")
                cx, cz, r, center_3d = fit_section_center_with_axis_projection(
                    pts, tan_slope, projection_y=y_value
                )
                x2d, z2d, origin, u, v = project_points_to_axis_section(
                    pts, tan_slope, projection_y=y_value
                )
                cu, cv, _ = fit_circle_2d(x2d, z2d)
                section_results.append({
                    "x2d": x2d,
                    "z2d": z2d,
                    "center_2d": (cu, cv, r),
                    "center_3d": center_3d,
                    "point_sources": section_point_sources[i],
                })
                raw_centers.append({"x": cx, "y": y_value, "z": cz})
                raw_radii.append(r)

            corrected_radii = [max(r - radius_correction, 0.0) for r in raw_radii]
            dev = deviation_at_y(raw_centers[0], raw_centers[1], raw_centers[2])

            self.last_result_data = {
                "tan_slope": tan_slope,
                "radius_correction": radius_correction,
                "centers": [
                    {"section": i + 1, "x": c["x"], "y": c["y"], "z": c["z"]}
                    for i, c in enumerate(raw_centers)
                ],
                "raw_radii": raw_radii,
                "corrected_radii": corrected_radii,
                "deviation": dev,
                "sections": section_results,
                "valid_point_counts": valid_point_counts,
            }

            self._clear_result(clear_data=False)
            self._append_result("=== 输入信息 ===")
            self._append_result("轴线方向: +Y 且 +Z 爬升")
            self._append_result(f"坡度 tan 值: {tan_slope:.3f}")
            self._append_result(f"半径修正值(mm): {radius_correction:.3f}")
            self._append_result("")

            self._append_result("=== 各档拟合结果（已先投影到垂直轴线平面）===")
            for i, c in enumerate(raw_centers):
                self._append_result(
                    f"{i+1}档: 有效数据点数量={valid_point_counts[i]}, "
                    f"圆心(mm)=({c['x']:.3f}, {c['y']:.3f}, {c['z']:.3f}), "
                    f"拟合半径(mm)={raw_radii[i]:.3f}, 修正后半径(mm)={corrected_radii[i]:.3f}"
                )
            self._append_result("")

            self._append_result("=== 共线偏差分析（二档相对一档-三档连线）===")
            self._append_result(
                f"在 y2 处 1-3 连线点(mm): X={dev['x_line']:.3f}, Z={dev['z_line']:.3f}"
            )
            self._append_result(
                f"X方向偏差(mm): {dev['dx']:.3f} (绝对值 {dev['abs_dx']:.3f})"
            )
            self._append_result(
                f"Z方向偏差(mm): {dev['dz']:.3f} (绝对值 {dev['abs_dz']:.3f})"
            )

        except Exception as exc:
            messagebox.showerror("分析失败", str(exc))


def main():
    root = tk.Tk()
    app = CircleCenterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()