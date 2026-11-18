# -*- coding: utf-8 -*-
"""托轮位置设置窗口及其绘图、测量辅助功能。"""

import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from turret_io import read_prism_file

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Polygon, Circle, Arc
from matplotlib.lines import Line2D
from matplotlib.text import Text, Annotation
from matplotlib.widgets import RectangleSelector


GEAR_NAMES = {1: '一档', 2: '二档', 3: '三档'}
SIDE_NAMES = {'L': '左', 'R': '右'}
END_NAMES = {'H': '高', 'L': '低'}

class TurretPositionWindow(tk.Toplevel):
    """托轮位置设置子窗口。"""

    def __init__(self, master):
        super().__init__(master)
        self.title("托轮位置设置 - 高低轴端及左右偏差")
        self.geometry("1500x980")

        self.point_vars = {}
        for gear in (1, 2, 3):
            for side in ('L', 'R'):
                for end in ('H', 'L'):
                    self.point_vars[(gear, side, end)] = (
                        tk.StringVar(value="0.0"),
                        tk.StringVar(value="0.0"),
                        tk.StringVar(value="0.0"),
                    )
        _gear1_defaults = {
            ('L', 'H'): ("1574.4", "2800", "1800"),
            ('L', 'L'): ("1559.5", "0", "1400"),
            ('R', 'H'): ("4520.8", "2800", "1800.8"),
            ('R', 'L'): ("4520.3", "0", "1399.2"),
        }
        for (side, end), vals in _gear1_defaults.items():
            vx, vy, vz = self.point_vars[(1, side, end)]
            vx.set(vals[0]); vy.set(vals[1]); vz.set(vals[2])

        self.plot_mode = tk.StringVar(value="A")

        self.base_y_bot_var = tk.StringVar(value="-100")
        self.base_W_y_var = tk.StringVar(value="3000")

        self.l1_var = tk.StringVar(value="100")
        self.l2_var = tk.StringVar(value="100")
        self.l3_var = tk.StringVar(value="100")
        self.l4_var = tk.StringVar(value="100")

        self.base1_x_var = tk.StringVar(value="0.0")
        self.baseline_x = tk.StringVar(value="6980")

        self.rect_x_margin = tk.StringVar(value="200")
        self.mag_L_var = tk.StringVar(value="20")
        self.mag_R_var = tk.StringVar(value="20")
        self.mag_z_var = tk.StringVar(value="20")
        self.view_zoom_var = tk.StringVar(value="1.0")
        self.current_gear = tk.IntVar(value=1)
        self.zoom_mode = tk.BooleanVar(value=False)
        self.rotate_dir_var = tk.StringVar(value="顺时针")

        self.zoom_xlim = None
        self.zoom_ylim = None
        self.offsets = {}
        self.prism_data = {}
        self.coord_offset = [0.0, 0.0, 0.0]

        self.draggable_groups = []
        self.active_group = None
        self.press_x = None
        self.press_y = None
        self.start_offset = 0
        self.start_data = []

        self._base_points = {}
        for key in self.point_vars:
            vals = []
            for v in self.point_vars[key]:
                try:
                    vals.append(float(v.get()))
                except ValueError:
                    vals.append(0.0)
            self._base_points[key] = vals
        self._base_y_bot = -100.0

        self.left_canvas = None

        self._build_menu()
        self._build_ui()

    def _build_menu(self):
        menubar = tk.Menu(self)
        measure_menu = tk.Menu(menubar, tearoff=0)
        measure_menu.add_command(label="棱镜位置解算...", command=self.open_prism_dialog)
        measure_menu.add_command(label="坐标系位移...", command=self.open_coord_offset_dialog)
        menubar.add_cascade(label="测量", menu=measure_menu)
        self.config(menu=menubar)

    def _sync_display_to_base(self):
        for key in self.point_vars:
            for i in (0, 1, 2):
                try:
                    display_val = float(self.point_vars[key][i].get())
                    self._base_points[key][i] = display_val - self.coord_offset[i]
                except ValueError:
                    pass
        try:
            self._base_y_bot = float(self.base_y_bot_var.get()) - self.coord_offset[1]
        except ValueError:
            pass

    def _refresh_display_from_base(self):
        for key in self.point_vars:
            for i in (0, 1, 2):
                val = self._base_points[key][i] + self.coord_offset[i]
                self.point_vars[key][i].set(f"{val:.4f}")
        self.base_y_bot_var.set(f"{self._base_y_bot + self.coord_offset[1]:.4f}")

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left_container = ttk.Frame(paned)
        paned.add(left_container, weight=0)

        self.left_canvas = tk.Canvas(left_container, borderwidth=0,
                                     highlightthickness=0, width=520)
        v_scroll = ttk.Scrollbar(left_container, orient="vertical",
                                 command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side="right", fill="y")
        self.left_canvas.pack(side="left", fill="both", expand=True)

        left = ttk.Frame(self.left_canvas)
        self.left_window = self.left_canvas.create_window((0, 0), window=left, anchor="nw")

        left.bind("<Configure>",
                  lambda e: self.left_canvas.configure(
                      scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>",
                              lambda e: self.left_canvas.itemconfigure(
                                  self.left_window, width=e.width))

        self.bind_all("<MouseWheel>", self._on_left_mousewheel)
        self.bind_all("<Button-4>", lambda e: self._on_left_mousewheel_linux(e, -1))
        self.bind_all("<Button-5>", lambda e: self._on_left_mousewheel_linux(e, 1))

        self._build_left(left)

        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        self._build_right(right)

    def _on_left_mousewheel(self, event):
        try:
            if self.left_canvas is None or not self.left_canvas.winfo_exists():
                return
            x, y = event.x_root, event.y_root
            cx = self.left_canvas.winfo_rootx()
            cy = self.left_canvas.winfo_rooty()
            cw = self.left_canvas.winfo_width()
            ch = self.left_canvas.winfo_height()
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                delta = event.delta
                if abs(delta) >= 120:
                    self.left_canvas.yview_scroll(int(-delta / 120), "units")
                else:
                    self.left_canvas.yview_scroll(-1 if delta > 0 else 1, "units")
        except Exception:
            pass

    def _on_left_mousewheel_linux(self, event, direction):
        try:
            if self.left_canvas is None or not self.left_canvas.winfo_exists():
                return
            x, y = event.x_root, event.y_root
            cx = self.left_canvas.winfo_rootx()
            cy = self.left_canvas.winfo_rooty()
            cw = self.left_canvas.winfo_width()
            ch = self.left_canvas.winfo_height()
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                self.left_canvas.yview_scroll(direction, "units")
        except Exception:
            pass

    def _build_left(self, parent):
        gear_frame = ttk.LabelFrame(parent, text="显示挡位")
        gear_frame.pack(fill="x", padx=4, pady=4)
        for g in (1, 2, 3):
            ttk.Radiobutton(gear_frame, text=GEAR_NAMES[g], value=g,
                            variable=self.current_gear,
                            command=self.plot).pack(side="left", padx=12, pady=4)

        frame = ttk.LabelFrame(parent, text="托轮轴端坐标 (mm)")
        frame.pack(fill="x", padx=4, pady=4)
        for j, h in enumerate(["点", "x", "y", "z"]):
            ttk.Label(frame, text=h, font=("", 9, "bold")).grid(row=0, column=j, padx=4, pady=2)
        row = 1
        for gear in (1, 2, 3):
            for side in ('L', 'R'):
                for end in ('H', 'L'):
                    label = f"{GEAR_NAMES[gear]}{SIDE_NAMES[side]}{END_NAMES[end]}"
                    ttk.Label(frame, text=label).grid(row=row, column=0, padx=4, pady=1, sticky="e")
                    vars_ = self.point_vars[(gear, side, end)]
                    for j, v in enumerate(vars_, start=1):
                        ttk.Entry(frame, textvariable=v, width=10).grid(
                            row=row, column=j, padx=2, pady=1)
                    row += 1
        ttk.Label(frame, text="坐标系: z 垂直地面向上, y 沿窑轴向, x 横向。",
                  foreground="#666", font=("", 8)).grid(
            row=row, column=0, columnspan=4, padx=4, pady=(4, 4), sticky="w")

        mode_frame = ttk.LabelFrame(parent, text="绘图模式（二选一）")
        mode_frame.pack(fill="x", padx=4, pady=4)
        ttk.Radiobutton(mode_frame, text="模式 A：已知基座下边缘 y + y 向宽度",
                        value="A", variable=self.plot_mode,
                        command=self._on_mode_change).pack(anchor="w", padx=6, pady=2)
        ttk.Radiobutton(mode_frame, text="模式 B：已知托轮轴到基座边缘距离 l1~l4",
                        value="B", variable=self.plot_mode,
                        command=self._on_mode_change).pack(anchor="w", padx=6, pady=2)

        self.frame_mode_A = ttk.LabelFrame(parent, text="模式 A 参数 (mm)")
        self.frame_mode_A.pack(fill="x", padx=4, pady=4)
        ttk.Label(self.frame_mode_A, text="基座下边缘 y:").grid(
            row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(self.frame_mode_A, textvariable=self.base_y_bot_var, width=12).grid(
            row=0, column=1, padx=4, pady=2)
        ttk.Label(self.frame_mode_A, text="基座 y 向宽度:").grid(
            row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(self.frame_mode_A, textvariable=self.base_W_y_var, width=12).grid(
            row=1, column=1, padx=4, pady=2)
        ttk.Label(self.frame_mode_A,
                  text="基座 y 范围 = [下边缘y, 下边缘y + 宽度]\n"
                       "x 向宽度自动取覆盖两条基准线，l1~l4 自动计算。",
                  foreground="#666", font=("", 8), justify="left").grid(
            row=2, column=0, columnspan=2, padx=4, pady=(2, 4), sticky="w")

        self.frame_mode_B = ttk.LabelFrame(parent, text="模式 B 参数 (mm)")
        self.frame_mode_B.pack(fill="x", padx=4, pady=4)
        labels_B = [
            ("左托轮高端 → 上边缘距离 l1:", self.l1_var),
            ("右托轮高端 → 上边缘距离 l2:", self.l2_var),
            ("左托轮低端 → 下边缘距离 l3:", self.l3_var),
            ("右托轮低端 → 下边缘距离 l4:", self.l4_var),
        ]
        for i, (lbl, var) in enumerate(labels_B):
            ttk.Label(self.frame_mode_B, text=lbl).grid(
                row=i, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(self.frame_mode_B, textvariable=var, width=12).grid(
                row=i, column=1, padx=4, pady=2)
        ttk.Label(self.frame_mode_B,
                  text="上/下边缘由两侧 H/L 点 + 各自距离确定，可为平行四边形。",
                  foreground="#666", font=("", 8)).grid(
            row=4, column=0, columnspan=2, padx=4, pady=(2, 4), sticky="w")

        param = ttk.LabelFrame(parent, text="通用绘图参数")
        param.pack(fill="x", padx=4, pady=4)
        ttk.Label(param, text="第一条基准线 x 坐标 (托轮系):").grid(
            row=0, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(param, textvariable=self.base1_x_var, width=12).grid(
            row=0, column=1, padx=4, pady=3)
        ttk.Label(param, text="两条基准线 x 间距:").grid(
            row=1, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(param, textvariable=self.baseline_x, width=12).grid(
            row=1, column=1, padx=4, pady=3)
        ttk.Label(param, text="基座 x 向两侧超出量:").grid(
            row=2, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(param, textvariable=self.rect_x_margin, width=12).grid(
            row=2, column=1, padx=4, pady=3)
        ttk.Label(param, text="左托轮倾斜放大倍数:").grid(
            row=3, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(param, textvariable=self.mag_L_var, width=12).grid(
            row=3, column=1, padx=4, pady=3)
        ttk.Label(param, text="右托轮倾斜放大倍数:").grid(
            row=4, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(param, textvariable=self.mag_R_var, width=12).grid(
            row=4, column=1, padx=4, pady=3)
        ttk.Label(param, text="Z 向高差放大倍数:").grid(
            row=5, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(param, textvariable=self.mag_z_var, width=12).grid(
            row=5, column=1, padx=4, pady=3)
        ttk.Label(param, text="矩形旋转方向:").grid(
            row=6, column=0, sticky="e", padx=4, pady=3)
        ttk.Combobox(param, textvariable=self.rotate_dir_var,
                     values=["顺时针", "逆时针"], state="readonly", width=10).grid(
            row=6, column=1, padx=4, pady=3, sticky="w")
        ttk.Button(param, text="绘制当前挡位", command=self.plot).grid(
            row=7, column=0, columnspan=2, pady=8, padx=4, sticky="ew")

        zoom_frame = ttk.LabelFrame(parent, text="视图缩放控制")
        zoom_frame.pack(fill="x", padx=4, pady=4)
        ttk.Checkbutton(zoom_frame, text="开启鼠标框选", variable=self.zoom_mode,
                        command=self.toggle_zoom_mode).grid(row=0, column=0, columnspan=2, pady=2, sticky="w")
        ttk.Label(zoom_frame, text="手动放大倍数:").grid(row=1, column=0, padx=4, pady=2, sticky="e")
        ttk.Entry(zoom_frame, textvariable=self.view_zoom_var, width=8).grid(
            row=1, column=1, padx=4, pady=2, sticky="w")
        ttk.Button(zoom_frame, text="重置视图", command=self.reset_view).grid(
            row=2, column=0, columnspan=2, pady=4)

        ttk.Label(parent,
                  text="提示: 图形生成后，可用鼠标左键拖动文字、线条或三角形。",
                  foreground="red", font=("", 9, "bold")).pack(padx=4, pady=(4, 2))

        sum_frame = ttk.LabelFrame(parent, text="偏差摘要")
        sum_frame.pack(fill="both", expand=True, padx=4, pady=(4, 12))
        self.txt_summary = tk.Text(sum_frame, height=14, width=50,
                                   font=("Consolas", 9), state="disabled")
        self.txt_summary.pack(fill="both", expand=True, padx=2, pady=2)

        self._on_mode_change()

    def _on_mode_change(self):
        if self.plot_mode.get() == "A":
            self.frame_mode_A.pack(fill="x", padx=4, pady=4, before=self.frame_mode_B)
            self.frame_mode_B.pack_forget()
        else:
            self.frame_mode_A.pack_forget()
            self.frame_mode_B.pack(fill="x", padx=4, pady=4)

    def _build_right(self, parent):
        self.fig = Figure(figsize=(9, 8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.09, right=0.98, top=0.96, bottom=0.06)
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self.ax.set_xlabel("x (mm) 横向")
        self.ax.set_ylabel("y (mm) 窑轴向")
        self.ax.set_title("请点击[绘制当前挡位]")

        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_release_event', self.on_release)

        self.rs = RectangleSelector(self.ax, self.on_select, useblit=True, button=[1],
                                    minspanx=5, minspany=5, spancoords='pixels', interactive=False)
        self.rs.set_active(False)
        self.canvas.draw()

    # ---------------- 坐标系偏移 ----------------
    def open_coord_offset_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("坐标系位移")
        dlg.geometry("480x360")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg,
                  text=("输入相对【原始托轮坐标系】的目标偏移 (dx, dy, dz)，\n"
                        "窑坐标系 = 原始托轮坐标 + 偏移。\n"
                        "每次应用均为绝对偏移值，不会与前一次累加。\n"
                        "基准线位置也会同步平移。"),
                  justify="left", foreground="#444").pack(padx=12, pady=8, anchor="w")

        frame = ttk.Frame(dlg)
        frame.pack(padx=12, pady=6, fill="x")
        ttk.Label(frame, text="dx (mm):").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        var_dx = tk.StringVar(value=f"{self.coord_offset[0]:.2f}")
        ttk.Entry(frame, textvariable=var_dx, width=14).grid(row=0, column=1, padx=4, pady=3)
        ttk.Label(frame, text="dy (mm):").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        var_dy = tk.StringVar(value=f"{self.coord_offset[1]:.2f}")
        ttk.Entry(frame, textvariable=var_dy, width=14).grid(row=1, column=1, padx=4, pady=3)
        ttk.Label(frame, text="dz (mm):").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        var_dz = tk.StringVar(value=f"{self.coord_offset[2]:.2f}")
        ttk.Entry(frame, textvariable=var_dz, width=14).grid(row=2, column=1, padx=4, pady=3)

        info_lbl = tk.Label(dlg, text=f"当前偏移: "
                                      f"dx={self.coord_offset[0]:.2f}, "
                                      f"dy={self.coord_offset[1]:.2f}, "
                                      f"dz={self.coord_offset[2]:.2f}",
                            fg="#1f5fa8", font=("", 9, "bold"))
        info_lbl.pack(padx=12, pady=4, anchor="w")

        ttk.Label(dlg, text="提示：清零请输入 (0, 0, 0)。",
                  foreground="#666").pack(padx=12, pady=(2, 0), anchor="w")

        def on_apply():
            try:
                dx = float(var_dx.get())
                dy = float(var_dy.get())
                dz = float(var_dz.get())
            except ValueError:
                messagebox.showerror("格式错误", "偏移值必须为数字", parent=dlg)
                return
            self._sync_display_to_base()
            self.coord_offset = [dx, dy, dz]
            self._refresh_display_from_base()
            dlg.destroy()
            self.plot()

        btns = ttk.Frame(dlg)
        btns.pack(pady=10)
        ttk.Button(btns, text="应用", command=on_apply, width=10).pack(side="left", padx=6)
        ttk.Button(btns, text="取消", command=dlg.destroy, width=10).pack(side="left", padx=6)

    # ---------------- 棱镜文件解析 ----------------
    def _read_prism_file(self, path):
        return read_prism_file(path)

    def _import_prism_file(self, target_vars, target_label):
        path = filedialog.askopenfilename(
            title=f"导入 {target_label} 坐标文件（原始单位：米）",
            filetypes=[("文本/CSV", "*.txt *.csv"),
                       ("Excel 文件", "*.xlsx *.xls"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            rows = self._read_prism_file(path)
        except Exception as e:
            messagebox.showerror("读取失败", f"{e}")
            return

        if not rows:
            messagebox.showwarning(
                "无有效数据",
                "文件中未找到有效坐标。\n\n"
                "支持的格式：\n"
                "  A. 轴标签矩阵（推荐）\n"
                "       X  1.5372  1.5368  1.5365  ...\n"
                "       Y  0.3062  0.3074  0.3069  ...\n"
                "       Z  0.6838  0.6843  0.6853  ...\n"
                "  B. 横向：每行 x y z\n"
                "  C. 纵向：一列数字，前 1/3 为 x、中 1/3 为 y、后 1/3 为 z\n"
                "  · 原始单位按米处理，导入后自动 ×1000 转毫米")
            return

        n = len(rows)
        mx = sum(r[0] for r in rows) / n
        my = sum(r[1] for r in rows) / n
        mz = sum(r[2] for r in rows) / n

        target_vars[0].set(f"{mx:.4f}")
        target_vars[1].set(f"{my:.4f}")
        target_vars[2].set(f"{mz:.4f}")

        messagebox.showinfo(
            "导入完成",
            f"{target_label} 已导入 {n} 条数据\n"
            f"（原始单位：米，已转为毫米）\n\n"
            f"算术平均值：\n"
            f"  x̄ = {mx:.4f} mm\n"
            f"  ȳ = {my:.4f} mm\n"
            f"  z̄ = {mz:.4f} mm")

    # ---------------- 棱镜位置解算 ----------------
    def open_prism_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("棱镜位置解算")
        dlg.geometry("860x700")
        dlg.transient(self)
        dlg.grab_set()

        gear = self.current_gear.get()

        header = ttk.Frame(dlg)
        header.pack(fill="x", padx=12, pady=8)
        ttk.Label(header, text=f"当前挡位：{GEAR_NAMES[gear]}",
                  font=("", 11, "bold")).pack(side="left")
        ttk.Label(header, text="  （左右两侧独立填写棱镜坐标及到端面距离）",
                  foreground="#666", font=("", 9)).pack(side="left")

        input_vars = {}

        def build_prism_row(parent, label_text, prefix):
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=6, pady=3)
            ttk.Label(row, text=label_text, width=10).pack(side="left")
            vars_triple = []
            for suffix, lbl in (('x', 'x'), ('y', 'y'), ('z', 'z')):
                key = (prefix, suffix)
                ttk.Label(row, text=f"{lbl}:").pack(side="left", padx=(6, 0))
                var = tk.StringVar(value="0.0")
                input_vars[key] = var
                vars_triple.append(var)
                ttk.Entry(row, textvariable=var, width=11).pack(side="left", padx=2)
            ttk.Button(row, text="导入...", width=8,
                       command=lambda tv=vars_triple,
                                      lbl=label_text: self._import_prism_file(tv, lbl)
                       ).pack(side="left", padx=(10, 0))

        for side in ('L', 'R'):
            frame = ttk.LabelFrame(dlg, text=f"{SIDE_NAMES[side]}托轮")
            frame.pack(fill="x", padx=12, pady=6)

            build_prism_row(frame, "高端棱镜:", side + 'H')
            build_prism_row(frame, "低端棱镜:", side + 'L')

            row = ttk.Frame(frame); row.pack(fill="x", padx=6, pady=3)
            ttk.Label(row, text="高端棱镜→高端面距离:").pack(side="left")
            var_dH = tk.StringVar(value="0.0")
            input_vars[(side, 'dH')] = var_dH
            ttk.Entry(row, textvariable=var_dH, width=12).pack(side="left", padx=3)
            ttk.Label(row, text="mm").pack(side="left")

            row = ttk.Frame(frame); row.pack(fill="x", padx=6, pady=3)
            ttk.Label(row, text="低端棱镜→低端面距离:").pack(side="left")
            var_dL = tk.StringVar(value="0.0")
            input_vars[(side, 'dL')] = var_dL
            ttk.Entry(row, textvariable=var_dL, width=12).pack(side="left", padx=3)
            ttk.Label(row, text="mm").pack(side="left")

        note_text = (
            "解算说明:\n"
            "  设高端棱镜 P_H、低端棱镜 P_L，单位方向向量 u = (P_L − P_H) / |P_L − P_H|\n"
            "  托轮轴高端  Q_H = P_H + d_H·u   (从高端棱镜向低端方向偏移 d_H)\n"
            "  托轮轴低端  Q_L = P_L − d_L·u   (从低端棱镜向高端方向偏移 d_L)\n"
            "  输入为【原始托轮坐标系】下的棱镜坐标，解算结果也作为原始坐标保存。\n\n"
            "文件导入支持的三种布局:\n"
            "  A. 轴标签矩阵（推荐）\n"
            "       X  1.5372  1.5368  1.5365  ...\n"
            "       Y  0.3062  0.3074  0.3069  ...\n"
            "       Z  0.6838  0.6843  0.6853  ...\n"
            "  B. 横向：每行 x y z\n"
            "  C. 纵向：一列数字，前 1/3 为 x、中 1/3 为 y、后 1/3 为 z\n"
            "  · 文件原始单位为米，导入后自动 ×1000 转毫米后求平均\n"
            "  · 每行【导入...】按钮只作用于对应棱镜，不影响其他棱镜"
        )
        ttk.Label(dlg, text=note_text,
                  foreground="#444", font=("Consolas", 9), justify="left").pack(
            fill="x", padx=14, pady=8)

        if gear in self.prism_data:
            for key, var in input_vars.items():
                if key in self.prism_data[gear]:
                    var.set(self.prism_data[gear][key])

        def on_calc():
            try:
                results = {}
                for side in ('L', 'R'):
                    Hx = float(input_vars[(side + 'H', 'x')].get())
                    Hy = float(input_vars[(side + 'H', 'y')].get())
                    Hz = float(input_vars[(side + 'H', 'z')].get())
                    Lx = float(input_vars[(side + 'L', 'x')].get())
                    Ly = float(input_vars[(side + 'L', 'y')].get())
                    Lz = float(input_vars[(side + 'L', 'z')].get())
                    dH = float(input_vars[(side, 'dH')].get())
                    dL = float(input_vars[(side, 'dL')].get())
                    dx, dy, dz = Lx - Hx, Ly - Hy, Lz - Hz
                    norm = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if norm < 1e-9:
                        messagebox.showerror("错误",
                                             f"{SIDE_NAMES[side]}托轮的高低端棱镜重合",
                                             parent=dlg)
                        return
                    ux, uy, uz = dx / norm, dy / norm, dz / norm
                    Qx_H = Hx + dH * ux; Qy_H = Hy + dH * uy; Qz_H = Hz + dH * uz
                    Qx_L = Lx - dL * ux; Qy_L = Ly - dL * uy; Qz_L = Lz - dL * uz
                    results[side] = ((Qx_H, Qy_H, Qz_H), (Qx_L, Qy_L, Qz_L))

                for side in ('L', 'R'):
                    (Qx_H, Qy_H, Qz_H), (Qx_L, Qy_L, Qz_L) = results[side]
                    self._base_points[(gear, side, 'H')] = [Qx_H, Qy_H, Qz_H]
                    self._base_points[(gear, side, 'L')] = [Qx_L, Qy_L, Qz_L]

                self._refresh_display_from_base()
                self.prism_data[gear] = {k: v.get() for k, v in input_vars.items()}
                messagebox.showinfo("完成",
                                    f"已解算并填入{GEAR_NAMES[gear]}的托轮轴高端/低端坐标",
                                    parent=dlg)
                dlg.destroy()
                self.plot()
            except ValueError:
                messagebox.showerror("格式错误", "所有输入必须为有效数字", parent=dlg)

        btns = ttk.Frame(dlg); btns.pack(pady=12)
        ttk.Button(btns, text="计算并填入", command=on_calc, width=14).pack(side="left", padx=6)
        ttk.Button(btns, text="关闭", command=dlg.destroy, width=10).pack(side="left", padx=6)

    # ---------------- 缩放控制 ----------------
    def toggle_zoom_mode(self):
        self.rs.set_active(self.zoom_mode.get())
        if self.zoom_mode.get():
            self.ax.set_title("框选放大模式：请按住鼠标左键框选区域")
        else:
            self.ax.set_title("拖拽模式：请按住鼠标左键拖动文字或线条")
        self.canvas.draw_idle()

    def on_select(self, eclick, erelease):
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        if x1 is not None and x2 is not None:
            self.zoom_xlim = [min(x1, x2), max(x1, x2)]
            self.zoom_ylim = [min(y1, y2), max(y1, y2)]
            self.ax.set_xlim(self.zoom_xlim)
            self.ax.set_ylim(self.zoom_ylim)
            self.canvas.draw_idle()

    def reset_view(self):
        self.zoom_xlim = None
        self.zoom_ylim = None
        self.view_zoom_var.set("1.0")
        self.plot()

    # ---------------- 拖拽事件 ----------------
    def on_press(self, event):
        if self.zoom_mode.get() or event.inaxes != self.ax:
            return
        for group in self.draggable_groups:
            if group['type'] in ('dim_h', 'dim_v'):
                artists = [group['l1'], group['l2'], group['l3'], group['t']]
            elif group['type'] == 'group':
                artists = group['artists']
            else:
                artists = []

            for artist in artists:
                contains, _ = artist.contains(event)
                if contains:
                    self.active_group = group
                    self.press_x = event.xdata
                    self.press_y = event.ydata
                    if group['type'] in ('dim_h', 'dim_v'):
                        self.start_offset = group['offset']
                    else:
                        self.start_data = []
                        for a in artists:
                            if isinstance(a, Line2D):
                                self.start_data.append((list(a.get_xdata()), list(a.get_ydata())))
                            elif isinstance(a, Annotation):
                                self.start_data.append((tuple(a.get_position()), tuple(a.xy)))
                            elif isinstance(a, Text):
                                self.start_data.append(a.get_position())
                            elif isinstance(a, Circle):
                                self.start_data.append(a.center)
                            elif isinstance(a, Arc):
                                ctr = getattr(a, 'center', None)
                                if ctr is None:
                                    ctr = getattr(a, '_center', (0.0, 0.0))
                                self.start_data.append((float(ctr[0]), float(ctr[1])))
                            elif isinstance(a, Polygon):
                                verts = a.get_xy()
                                self.start_data.append([(float(v[0]), float(v[1])) for v in verts])
                            else:
                                self.start_data.append((0.0, 0.0))
                    return

    def on_motion(self, event):
        if self.zoom_mode.get() or event.inaxes != self.ax or self.active_group is None:
            return
        dx = event.xdata - self.press_x
        dy = event.ydata - self.press_y

        group = self.active_group
        if group['type'] == 'dim_h':
            new_offset = self.start_offset + dy
            y_line = group['y_ref'] + new_offset
            x1, x2 = group['x1'], group['x2']
            y1 = group.get('y1', group['y_ref']); y2 = group.get('y2', group['y_ref'])
            group['l1'].set_data([x1, x1], [y1, y_line])
            group['l2'].set_data([x2, x2], [y2, y_line])
            group['l3'].set_data([x1, x2], [y_line, y_line])
            arr = group.get('arr')
            if arr is not None:
                arr.xy = (x2, y_line); arr.set_position((x1, y_line))
            group['t'].set_position(((x1 + x2) / 2, y_line + 50))
            group['temp_offset'] = new_offset

        elif group['type'] == 'dim_v':
            new_offset = self.start_offset + dx
            x_line = group['x_ref'] + new_offset
            y1, y2 = group['y1'], group['y2']
            group['l1'].set_data([group['x_ref'], x_line], [y1, y1])
            group['l2'].set_data([group['x_ref'], x_line], [y2, y2])
            group['l3'].set_data([x_line, x_line], [y1, y2])
            arr = group.get('arr')
            if arr is not None:
                arr.xy = (x_line, y2); arr.set_position((x_line, y1))
            group['t'].set_position((x_line + 50, (y1 + y2) / 2))
            group['temp_offset'] = new_offset

        elif group['type'] == 'group':
            artists = group['artists']
            for i, a in enumerate(artists):
                if isinstance(a, Line2D):
                    xdata, ydata = self.start_data[i]
                    a.set_data([v + dx for v in xdata], [v + dy for v in ydata])
                elif isinstance(a, Annotation):
                    xytext, xy = self.start_data[i]
                    a.set_position((xytext[0] + dx, xytext[1] + dy))
                    a.xy = (xy[0] + dx, xy[1] + dy)
                elif isinstance(a, Text):
                    x, y = self.start_data[i]
                    a.set_position((x + dx, y + dy))
                elif isinstance(a, Circle):
                    x, y = self.start_data[i]
                    a.center = (x + dx, y + dy)
                elif isinstance(a, Arc):
                    x, y = self.start_data[i]
                    try:
                        a.set_center((x + dx, y + dy))
                    except AttributeError:
                        a._center = (x + dx, y + dy)
                elif isinstance(a, Polygon):
                    verts = self.start_data[i]
                    a.set_xy([(v[0] + dx, v[1] + dy) for v in verts])

        self.canvas.draw_idle()

    def on_release(self, event):
        if self.active_group is not None:
            if 'key' in self.active_group and 'temp_offset' in self.active_group:
                self.offsets[self.active_group['key']] = self.active_group['temp_offset']
        self.active_group = None
        self.start_data = []

    # ---------------- 尺寸标注函数 ----------------
    def _draw_horizontal_dim(self, x1, x2, y_ref, text, offset_y, key, y1=None, y2=None):
        if y1 is None: y1 = y_ref
        if y2 is None: y2 = y_ref
        if key in self.offsets: offset_y = self.offsets[key]
        y_line = y_ref + offset_y
        l1, = self.ax.plot([x1, x1], [y1, y_line], color='black', lw=0.5, zorder=10, picker=5)
        l2, = self.ax.plot([x2, x2], [y2, y_line], color='black', lw=0.5, zorder=10, picker=5)
        l3, = self.ax.plot([x1, x2], [y_line, y_line], color='black', lw=0.4, zorder=10, picker=5)
        arr = None
        if abs(x2 - x1) > 1e-6:
            arr = self.ax.annotate('', xy=(x2, y_line), xytext=(x1, y_line),
                                   arrowprops=dict(arrowstyle='<|-|>', color='black', lw=0.5,
                                                   shrinkA=0, shrinkB=0, mutation_scale=7),
                                   zorder=11)
        t = self.ax.text((x1 + x2) / 2, y_line + 50, text, ha='center', va='bottom',
                         color='black', fontsize=8, zorder=12, picker=5,
                         bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
        return {'type': 'dim_h', 'key': key, 'x1': x1, 'x2': x2, 'y_ref': y_ref,
                'y1': y1, 'y2': y2, 'offset': offset_y,
                'l1': l1, 'l2': l2, 'l3': l3, 'arr': arr, 't': t}

    def _draw_vertical_dim(self, x_ref, y1, y2, text, offset_x, key):
        if key in self.offsets: offset_x = self.offsets[key]
        x_line = x_ref + offset_x
        l1, = self.ax.plot([x_ref, x_line], [y1, y1], color='black', lw=0.5, zorder=10, picker=5)
        l2, = self.ax.plot([x_ref, x_line], [y2, y2], color='black', lw=0.5, zorder=10, picker=5)
        l3, = self.ax.plot([x_line, x_line], [y1, y2], color='black', lw=0.4, zorder=10, picker=5)
        arr = None
        if abs(y2 - y1) > 1e-6:
            arr = self.ax.annotate('', xy=(x_line, y2), xytext=(x_line, y1),
                                   arrowprops=dict(arrowstyle='<|-|>', color='black', lw=0.5,
                                                   shrinkA=0, shrinkB=0, mutation_scale=7),
                                   zorder=11)
        t = self.ax.text(x_line + 50, (y1 + y2) / 2, text, ha='left', va='center',
                         color='black', fontsize=8, zorder=12, picker=5,
                         bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
        return {'type': 'dim_v', 'key': key, 'x_ref': x_ref, 'y1': y1, 'y2': y2, 'offset': offset_x,
                'l1': l1, 'l2': l2, 'l3': l3, 'arr': arr, 't': t}

    def _draw_rect_center_marker(self, gear, cx, cy, x_len, y_len):
        is_cw = self.rotate_dir_var.get() == "顺时针"
        gear_text = self.ax.text(cx, cy, f"{gear}#", ha='center', va='center',
                                 fontsize=12, color='black', zorder=14, picker=5)
        r_arrow = max(min(x_len, y_len) * 0.15, 120)
        arc = Arc((cx, cy), 2 * r_arrow, 2 * r_arrow, angle=0,
                  theta1=130, theta2=410, color='black', lw=0.9, zorder=11, picker=5)
        self.ax.add_patch(arc)
        arrow_head_deg = 270
        tangent_deg = 180 if is_cw else 0
        head_rad = math.radians(arrow_head_deg); tan_rad = math.radians(tangent_deg)
        tip_x = cx + r_arrow * math.cos(head_rad)
        tip_y = cy + r_arrow * math.sin(head_rad)
        arrow_len = max(r_arrow * 0.35, 30)
        arrow_half_w = arrow_len * 0.45
        base_x = tip_x - arrow_len * math.cos(tan_rad)
        base_y = tip_y - arrow_len * math.sin(tan_rad)
        perp_rad = tan_rad + math.pi / 2
        wing1 = (base_x + arrow_half_w * math.cos(perp_rad),
                 base_y + arrow_half_w * math.sin(perp_rad))
        wing2 = (base_x - arrow_half_w * math.cos(perp_rad),
                 base_y - arrow_half_w * math.sin(perp_rad))
        arrow_tri = Polygon([(tip_x, tip_y), wing1, wing2], closed=True,
                            facecolor='black', edgecolor='black', zorder=12, picker=5)
        self.ax.add_patch(arrow_tri)
        return {'type': 'group', 'artists': [gear_text, arc, arrow_tri]}

    # ---------------- 数据读取 ----------------
    def _read_params(self):
        try:
            base1_x = float(self.base1_x_var.get())
            X = float(self.baseline_x.get())
            m = float(self.rect_x_margin.get())
            mag_L = float(self.mag_L_var.get())
            mag_R = float(self.mag_R_var.get())
            mag_z = float(self.mag_z_var.get())
            if self.plot_mode.get() == "A":
                y_bot = float(self.base_y_bot_var.get())
                W_y = float(self.base_W_y_var.get())
                if m < 0 or mag_L < 1 or mag_R < 1 or mag_z < 1 or W_y <= 0:
                    raise ValueError
                return ('A', base1_x, X, m, mag_L, mag_R, mag_z, y_bot, W_y)
            else:
                l1 = float(self.l1_var.get())
                l2 = float(self.l2_var.get())
                l3 = float(self.l3_var.get())
                l4 = float(self.l4_var.get())
                if m < 0 or mag_L < 1 or mag_R < 1 or mag_z < 1:
                    raise ValueError
                return ('B', base1_x, X, m, mag_L, mag_R, mag_z, l1, l2, l3, l4)
        except ValueError:
            messagebox.showerror("参数错误", "参数必须为有效数字，倍数需 >= 1，宽度需 > 0")
            return None

    def _read_points(self):
        pts = {}
        for key, (vx, vy, vz) in self.point_vars.items():
            try:
                pts[key] = (float(vx.get()), float(vy.get()), float(vz.get()))
            except ValueError:
                label = f"{GEAR_NAMES[key[0]]}{SIDE_NAMES[key[1]]}{END_NAMES[key[2]]}"
                messagebox.showerror("坐标错误", f"{label} 坐标必须为数字")
                return None
        return pts

    # ---------------- 偏差摘要 ----------------
    def _update_summary(self, mode, gear, pts, X, m, mag_L, mag_R, mag_z,
                        base_info, z_info, line1_x_abs):
        lines = [f"{GEAR_NAMES[gear]}托轮偏差摘要  [模式 {mode}]", "=" * 44, ""]
        if mag_L > 1 or mag_R > 1 or mag_z > 1:
            lines.append(f"⚠ 倾斜放大(L:{mag_L}/R:{mag_R})，Z向放大:{mag_z}倍")
            lines.append("")

        line2_x_abs = line1_x_abs + X
        lines.append(f"基准线 1 x = {line1_x_abs:.2f}，基准线 2 x = {line2_x_abs:.2f}，间距 = {X:.2f}")
        lines.append("")

        if mode == "A":
            lines.append(f"模式 A：基座 y 范围 [{base_info['y_bot']:.2f}, {base_info['y_top']:.2f}]")
            lines.append(f"  左高端到上边缘 l1 = {base_info['l1']:.2f} mm")
            lines.append(f"  右高端到上边缘 l2 = {base_info['l2']:.2f} mm")
            lines.append(f"  左低端到下边缘 l3 = {base_info['l3']:.2f} mm")
            lines.append(f"  右低端到下边缘 l4 = {base_info['l4']:.2f} mm")
        else:
            lines.append(f"模式 B：输入距离 l1={base_info['l1']:.2f}, "
                         f"l2={base_info['l2']:.2f}, "
                         f"l3={base_info['l3']:.2f}, l4={base_info['l4']:.2f}")
        lines.append("")

        for side in ('L', 'R'):
            h = pts[(gear, side, 'H')]; l = pts[(gear, side, 'L')]
            base_x = line1_x_abs if side == 'L' else line2_x_abs
            if side in z_info:
                dx_new = abs(z_info[side]['x_hi'] - z_info[side]['x_lo'])
                d_hi = abs(z_info[side]['x_hi'] - base_x)
                d_lo = abs(z_info[side]['x_lo'] - base_x)
            else:
                d_hi = d_lo = dx_new = 0.0

            dz_true = abs(h[2] - l[2])
            dy_true = abs(h[1] - l[1])
            tan_val = (dz_true / dy_true * 100) if dy_true > 1e-6 else 0.0
            theta_deg_true = math.degrees(math.atan(tan_val / 100.0))

            lines.append(f"{SIDE_NAMES[side]}托轮:")
            lines.append(f"  端点计算 tanθ = {tan_val:.4f} %  (θ ≈ {theta_deg_true:.4f}°)")
            lines.append(f"  上边缘交点 a 距基准线 = {d_hi:.2f} mm")
            lines.append(f"  下边缘交点 b 距基准线 = {d_lo:.2f} mm")
            lines.append(f"  水平偏差 = |x_a - x_b| = {dx_new:.2f} mm")

        if 'L' in z_info and 'R' in z_info:
            z_top_L = z_info['L']['z_top']
            z_top_R = z_info['R']['z_top']
            z_bot_L = z_info['L']['z_bot']
            z_bot_R = z_info['R']['z_bot']
            lines.append("")
            lines.append("Z 向高差 (右 - 左)，由 a/b 交点 z 坐标求得:")
            lines.append(f"  a 点（上边缘交点）: za_R - za_L = {z_top_R - z_top_L:+.2f} mm")
            lines.append(f"    za_L = {z_top_L:.2f}, za_R = {z_top_R:.2f}")
            lines.append(f"  b 点（下边缘交点）: zb_R - zb_L = {z_bot_R - z_bot_L:+.2f} mm")
            lines.append(f"    zb_L = {z_bot_L:.2f}, zb_R = {z_bot_R:.2f}")

        self.txt_summary.config(state="normal")
        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", "\n".join(lines))
        self.txt_summary.config(state="disabled")

    # ---------------- 绘图主函数 ----------------
    def plot(self):
        self._sync_display_to_base()

        params = self._read_params()
        if params is None:
            return
        mode = params[0]
        base1_x = params[1]
        X = params[2]
        m = params[3]
        mag_L = params[4]
        mag_R = params[5]
        mag_z = params[6]

        pts = self._read_points()
        if pts is None:
            return
        gear = self.current_gear.get()

        ax = self.ax
        ax.clear()
        ax.grid(True, linestyle="--", alpha=0.4)
        self.draggable_groups.clear()
        self.active_group = None

        x_offset = self.coord_offset[0]
        line1_x_abs = base1_x + x_offset
        line2_x_abs = line1_x_abs + X

        ys = [pts[(gear, side, end)][1] for side in ('L', 'R') for end in ('H', 'L')]
        y_min, y_max = min(ys), max(ys)
        y_pad = max(1000.0, (y_max - y_min) * 1.2)
        y_lo_plot, y_hi_plot = y_min - y_pad, y_max + y_pad

        ax.plot([line1_x_abs, line1_x_abs], [y_lo_plot, y_hi_plot], color='red',
                linestyle='--', linewidth=1.5, label="基准线 1")
        ax.plot([line2_x_abs, line2_x_abs], [y_lo_plot, y_hi_plot], color='red',
                linestyle='--', linewidth=1.2, label="基准线 2")

        y_mid = (y_lo_plot + y_hi_plot) / 2.0
        if abs(X) > 1e-6:
            g = self._draw_horizontal_dim(line1_x_abs, line2_x_abs, y_mid,
                                          f"{abs(X):.1f}", 300, 'base_X')
            self.draggable_groups.append(g)

        hL, lL = pts[(gear, 'L', 'H')], pts[(gear, 'L', 'L')]
        hR, lR = pts[(gear, 'R', 'H')], pts[(gear, 'R', 'L')]

        x_min_line = min(line1_x_abs, line2_x_abs)
        x_max_line = max(line1_x_abs, line2_x_abs)

        if mode == "A":
            y_bot = params[7]
            W_y = params[8]
            y_top = y_bot + W_y
            x_left = x_min_line - m
            x_right = x_max_line + m
            k_hi, b_hi = 0.0, y_top
            k_lo, b_lo = 0.0, y_bot
            l1_calc = abs(hL[1] - y_top); l2_calc = abs(hR[1] - y_top)
            l3_calc = abs(lL[1] - y_bot); l4_calc = abs(lR[1] - y_bot)
            base_info = {'l1': l1_calc, 'l2': l2_calc, 'l3': l3_calc, 'l4': l4_calc,
                         'y_bot': y_bot, 'y_top': y_top}
        else:
            l1_in, l2_in, l3_in, l4_in = params[7], params[8], params[9], params[10]
            x_left = x_min_line - m
            x_right = x_max_line + m

            h_y_avg = (hL[1] + hR[1]) / 2
            l_y_avg = (lL[1] + lR[1]) / 2
            if h_y_avg > l_y_avg:
                y_hi_L = hL[1] - l1_in; y_hi_R = hR[1] - l2_in
                y_lo_L = lL[1] + l3_in; y_lo_R = lR[1] + l4_in
            else:
                y_hi_L = hL[1] + l1_in; y_hi_R = hR[1] + l2_in
                y_lo_L = lL[1] - l3_in; y_lo_R = lR[1] - l4_in

            if abs(hR[0] - hL[0]) > 1e-6:
                k_hi = (y_hi_R - y_hi_L) / (hR[0] - hL[0])
                b_hi = y_hi_L - k_hi * hL[0]
            else:
                k_hi, b_hi = 0.0, y_hi_L
            if abs(lR[0] - lL[0]) > 1e-6:
                k_lo = (y_lo_R - y_lo_L) / (lR[0] - lL[0])
                b_lo = y_lo_L - k_lo * lL[0]
            else:
                k_lo, b_lo = 0.0, y_lo_L
            base_info = {'l1': l1_in, 'l2': l2_in, 'l3': l3_in, 'l4': l4_in,
                         'y_bot': min(y_lo_L, y_lo_R), 'y_top': max(y_hi_L, y_hi_R)}

        y_top_left = k_hi * x_left + b_hi
        y_top_right = k_hi * x_right + b_hi
        y_bot_left = k_lo * x_left + b_lo
        y_bot_right = k_lo * x_right + b_lo

        poly_pts = [
            (x_left, y_bot_left),
            (x_right, y_bot_right),
            (x_right, y_top_right),
            (x_left, y_top_left),
        ]
        ax.add_patch(Polygon(poly_pts, closed=True, linewidth=1.2, edgecolor='black',
                             facecolor='none', linestyle='--', label="基座外框"))

        y_width_left = y_top_left - y_bot_left
        g = self._draw_vertical_dim(x_left, y_bot_left, y_top_left,
                                     f"Y:{y_width_left:.1f}", -600, 'base_Y')
        self.draggable_groups.append(g)

        z_info = {}
        for side in ('L', 'R'):
            h = pts[(gear, side, 'H')]
            l = pts[(gear, side, 'L')]
            mag = mag_L if side == 'L' else mag_R

            cx = (h[0] + l[0]) / 2.0
            cy = (h[1] + l[1]) / 2.0
            h_draw_x = cx + (h[0] - cx) * mag
            l_draw_x = cx + (l[0] - cx) * mag

            vx = h_draw_x - l_draw_x
            vy = h[1] - l[1]
            L_axis = math.hypot(vx, vy)
            if L_axis < 1e-6:
                continue
            ux, uy = vx / L_axis, vy / L_axis
            nx, ny = -uy, ux

            L_tire, w_tire = 800, 500
            P_tire = [
                (cx + L_tire / 2 * ux + w_tire / 2 * nx, cy + L_tire / 2 * uy + w_tire / 2 * ny),
                (cx - L_tire / 2 * ux + w_tire / 2 * nx, cy - L_tire / 2 * uy + w_tire / 2 * ny),
                (cx - L_tire / 2 * ux - w_tire / 2 * nx, cy - L_tire / 2 * uy - w_tire / 2 * ny),
                (cx + L_tire / 2 * ux - w_tire / 2 * nx, cy + L_tire / 2 * uy - w_tire / 2 * ny)
            ]
            ax.add_patch(Polygon(P_tire, closed=True, facecolor='white', edgecolor='black', lw=1.5, zorder=9))

            w_shaft = 100
            P_hi = [
                (h_draw_x + w_shaft / 2 * nx, h[1] + w_shaft / 2 * ny),
                (cx + L_tire / 2 * ux + w_shaft / 2 * nx, cy + L_tire / 2 * uy + w_shaft / 2 * ny),
                (cx + L_tire / 2 * ux - w_shaft / 2 * nx, cy + L_tire / 2 * uy - w_shaft / 2 * ny),
                (h_draw_x - w_shaft / 2 * nx, h[1] - w_shaft / 2 * ny)
            ]
            ax.add_patch(Polygon(P_hi, closed=True, facecolor='#dddddd', edgecolor='black', lw=1.0, zorder=8))
            P_lo = [
                (l_draw_x + w_shaft / 2 * nx, l[1] + w_shaft / 2 * ny),
                (cx - L_tire / 2 * ux + w_shaft / 2 * nx, cy - L_tire / 2 * uy + w_shaft / 2 * ny),
                (cx - L_tire / 2 * ux - w_shaft / 2 * nx, cy - L_tire / 2 * uy - w_shaft / 2 * ny),
                (l_draw_x - w_shaft / 2 * nx, l[1] - w_shaft / 2 * ny)
            ]
            ax.add_patch(Polygon(P_lo, closed=True, facecolor='#dddddd', edgecolor='black', lw=1.0, zorder=8))

            ax.plot(h_draw_x, h[1], 'ro', markersize=4, zorder=11)
            ax.plot(l_draw_x, l[1], 'ro', markersize=4, zorder=11)

            def find_intersect(h_pt, l_pt, k_e, b_e, h_dx, l_dx):
                hx, hy, hz = h_pt[0], h_pt[1], h_pt[2]
                lx, ly, lz = l_pt[0], l_pt[1], l_pt[2]
                denom = (hy - ly) - k_e * (hx - lx)
                if abs(denom) < 1e-9:
                    t = 1.0
                else:
                    t = (k_e * lx + b_e - ly) / denom
                x_real = lx + t * (hx - lx)
                y_real = ly + t * (hy - ly)
                z_real = lz + t * (hz - lz)
                x_draw = l_dx + t * (h_dx - l_dx)
                return x_real, y_real, z_real, x_draw

            a_x_real, a_y, a_z, a_x_draw = find_intersect(h, l, k_hi, b_hi, h_draw_x, l_draw_x)
            b_x_real, b_y, b_z, b_x_draw = find_intersect(h, l, k_lo, b_lo, h_draw_x, l_draw_x)

            ax.plot(a_x_draw, a_y, 'ro', markersize=4, zorder=12)
            ax.plot(b_x_draw, b_y, 'ro', markersize=4, zorder=12)

            z_info[side] = {'top': a_y, 'bot': b_y,
                            'z_top': a_z, 'z_bot': b_z,
                            'x_hi': a_x_real, 'x_lo': b_x_real,
                            'x_draw_hi': a_x_draw, 'x_draw_lo': b_x_draw}

            y_hi_at_H = k_hi * h[0] + b_hi
            y_lo_at_L = k_lo * l[0] + b_lo
            v_off = -400 if side == 'L' else 400
            g1 = self._draw_vertical_dim(h_draw_x, h[1], y_hi_at_H,
                                          f"{abs(h[1] - y_hi_at_H):.1f}",
                                          v_off, f'v_off_hi_{side}')
            self.draggable_groups.append(g1)
            g2 = self._draw_vertical_dim(l_draw_x, l[1], y_lo_at_L,
                                          f"{abs(l[1] - y_lo_at_L):.1f}",
                                          v_off, f'v_off_lo_{side}')
            self.draggable_groups.append(g2)

            base_x_draw = line1_x_abs if side == 'L' else line2_x_abs
            base_x_real = line1_x_abs if side == 'L' else line2_x_abs
            g3 = self._draw_horizontal_dim(base_x_draw, a_x_draw, a_y,
                                            f"{abs(a_x_real - base_x_real):.1f}",
                                            150, f'h_off_hi_{side}')
            self.draggable_groups.append(g3)
            g4 = self._draw_horizontal_dim(base_x_draw, b_x_draw, b_y,
                                            f"{abs(b_x_real - base_x_real):.1f}",
                                            -150, f'h_off_lo_{side}')
            self.draggable_groups.append(g4)

        y_all = [y_top_left, y_top_right, y_bot_left, y_bot_right]
        cx_rect_all = (x_left + x_right) / 2.0
        cy_rect_all = (min(y_all) + max(y_all)) / 2.0
        marker = self._draw_rect_center_marker(gear, cx_rect_all, cy_rect_all,
                                                x_right - x_left, max(y_all) - min(y_all))
        self.draggable_groups.append(marker)

        if 'L' in z_info and 'R' in z_info:
            for side in ('L', 'R'):
                dx_val = abs(z_info[side]['x_hi'] - z_info[side]['x_lo'])
                y_mid_s = (z_info[side]['top'] + z_info[side]['bot']) / 2
                g = self._draw_horizontal_dim(z_info[side]['x_draw_hi'],
                                               z_info[side]['x_draw_lo'],
                                               y_mid_s, f"{dx_val:.1f}", 0, f'dx_{side}',
                                               y1=z_info[side]['top'], y2=z_info[side]['bot'])
                self.draggable_groups.append(g)

            z_top_L = z_info['L']['z_top']
            z_top_R = z_info['R']['z_top']
            y_top_base = y_hi_plot + 1500
            z_base = min(z_top_L, z_top_R)
            y_L_top = y_top_base + (z_top_L - z_base) * mag_z
            y_R_top = y_top_base + (z_top_R - z_base) * mag_z
            x_circ_L = x_left + (x_right - x_left) * 0.3
            x_circ_R = x_left + (x_right - x_left) * 0.7
            r_circ = 120

            c1 = Circle((x_circ_L, y_L_top), r_circ, fill=False, ec='black', lw=1.5, picker=5)
            c2 = Circle((x_circ_R, y_R_top), r_circ, fill=False, ec='black', lw=1.5, picker=5)
            ax.add_patch(c1); ax.add_patch(c2)
            d1, = ax.plot(x_circ_L, y_L_top, 'ro', ms=3, picker=5)
            d2, = ax.plot(x_circ_R, y_R_top, 'ro', ms=3, picker=5)
            cl1, = ax.plot([x_circ_L, x_circ_R], [y_L_top, y_L_top], color='black', lw=0.6, ls=':', picker=5)
            cl2, = ax.plot([x_circ_R, x_circ_L], [y_R_top, y_R_top], color='black', lw=0.6, ls=':', picker=5)
            dim_top = self._draw_vertical_dim(x_circ_R + r_circ + 100, y_L_top, y_R_top,
                                               f"Δza={z_top_R - z_top_L:+.2f}", 150, 'dz_top')
            title_top = ax.text((x_circ_L + x_circ_R) / 2, y_top_base + 400,
                                f"高端垂直面示意图 (za, 放大{mag_z}倍)", ha='center', fontsize=10,
                                fontweight='bold', picker=5,
                                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
            self.draggable_groups.append({'type': 'group', 'artists': [
                c1, c2, d1, d2, cl1, cl2, title_top,
                dim_top['l1'], dim_top['l2'], dim_top['l3'], dim_top['t']]})

            z_bot_L = z_info['L']['z_bot']
            z_bot_R = z_info['R']['z_bot']
            y_bot_base = y_lo_plot - 1500
            z_base2 = min(z_bot_L, z_bot_R)
            y_L_bot = y_bot_base + (z_bot_L - z_base2) * mag_z
            y_R_bot = y_bot_base + (z_bot_R - z_base2) * mag_z
            c3 = Circle((x_circ_L, y_L_bot), r_circ, fill=False, ec='black', lw=1.5, picker=5)
            c4 = Circle((x_circ_R, y_R_bot), r_circ, fill=False, ec='black', lw=1.5, picker=5)
            ax.add_patch(c3); ax.add_patch(c4)
            d3, = ax.plot(x_circ_L, y_L_bot, 'ro', ms=3, picker=5)
            d4, = ax.plot(x_circ_R, y_R_bot, 'ro', ms=3, picker=5)
            cl3, = ax.plot([x_circ_L, x_circ_R], [y_L_bot, y_L_bot], color='black', lw=0.6, ls=':', picker=5)
            cl4, = ax.plot([x_circ_R, x_circ_L], [y_R_bot, y_R_bot], color='black', lw=0.6, ls=':', picker=5)
            dim_bot = self._draw_vertical_dim(x_circ_R + r_circ + 100, y_L_bot, y_R_bot,
                                               f"Δzb={z_bot_R - z_bot_L:+.2f}", 150, 'dz_bot')
            title_bot = ax.text((x_circ_L + x_circ_R) / 2, y_bot_base - 500,
                                f"低端垂直面示意图 (zb, 放大{mag_z}倍)", ha='center', fontsize=10,
                                fontweight='bold', picker=5,
                                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
            self.draggable_groups.append({'type': 'group', 'artists': [
                c3, c4, d3, d4, cl3, cl4, title_bot,
                dim_bot['l1'], dim_bot['l2'], dim_bot['l3'], dim_bot['t']]})

            def draw_tan_triangle(x_anchor, y_center, tan_val, side_label, y_len):
                L_y = max(y_len / 4.0, 200.0)
                ratio = max(0.25, min(1.0, 0.25 + tan_val / 100.0 * 3.0))
                L_z_visual = L_y * ratio
                p1 = (x_anchor, y_center - L_y / 2)
                p2 = (x_anchor, y_center + L_y / 2)
                p3 = (x_anchor + L_z_visual, y_center + L_y / 2)
                l1, = ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color='black', lw=1.5, picker=5)
                l2, = ax.plot([p2[0], p3[0]], [p2[1], p3[1]], color='black', lw=1.5, picker=5)
                l3, = ax.plot([p3[0], p1[0]], [p3[1], p1[1]], color='black', lw=1.5, picker=5)
                theta_draw_deg = math.degrees(math.atan2(L_z_visual, L_y))
                r_arc = L_y / 3.0
                arc = Arc(p1, 2 * r_arc, 2 * r_arc, angle=0,
                          theta1=90.0 - theta_draw_deg, theta2=90.0,
                          color='black', lw=1.2, zorder=12)
                ax.add_patch(arc)
                lbl_x = p1[0] - max(L_y * 0.18, 120.0)
                theta_lbl = ax.text(lbl_x, y_center, r"$\theta$", ha='center', va='center',
                                    fontsize=9, color='black', zorder=13, picker=5)
                t = ax.text(x_anchor + L_z_visual / 2, y_center - L_y / 2 - 100,
                            f"tanθ={tan_val:.4f}%\n({side_label})",
                            ha='center', va='top', fontsize=9, fontweight='bold', picker=5,
                            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
                return {'type': 'group', 'artists': [l1, l2, l3, arc, theta_lbl, t]}

            dy_L = abs(hL[1] - lL[1]); dz_L = abs(hL[2] - lL[2])
            tan_L = (dz_L / dy_L * 100) if dy_L > 1e-6 else 0.0
            tri_L = draw_tan_triangle(x_left - 1500, (z_info['L']['top'] + z_info['L']['bot']) / 2,
                                       tan_L, "左", max(y_all) - min(y_all))
            self.draggable_groups.append(tri_L)
            dy_R = abs(hR[1] - lR[1]); dz_R = abs(hR[2] - lR[2])
            tan_R = (dz_R / dy_R * 100) if dy_R > 1e-6 else 0.0
            tri_R = draw_tan_triangle(x_right + 1500, (z_info['R']['top'] + z_info['R']['bot']) / 2,
                                       tan_R, "右", max(y_all) - min(y_all))
            self.draggable_groups.append(tri_R)

        ax.set_xlabel("x (mm) 横向")
        ax.set_ylabel("y (mm) 窑轴向")
        ax.set_title(f"{GEAR_NAMES[gear]}托轮倾斜与高差  [模式 {mode}]  "
                     f"(L放大{mag_L}/R放大{mag_R}/Z放大{mag_z})")

        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), loc="upper left", fontsize=8)

        if self.zoom_xlim and self.zoom_ylim:
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlim(self.zoom_xlim)
            ax.set_ylim(self.zoom_ylim)
        else:
            ax.set_aspect("equal", adjustable="box")
            ax.margins(0.15)
            try:
                factor = float(self.view_zoom_var.get())
            except ValueError:
                factor = 1.0
            if factor > 1.0:
                xlim = ax.get_xlim(); ylim = ax.get_ylim()
                cx = (xlim[0] + xlim[1]) / 2; cy = (ylim[0] + ylim[1]) / 2
                w = (xlim[1] - xlim[0]) / factor; h = (ylim[1] - ylim[0]) / factor
                ax.set_xlim(cx - w / 2, cx + w / 2)
                ax.set_ylim(cy - h / 2, cy + h / 2)

        self.rs.set_active(self.zoom_mode.get())
        self.canvas.draw_idle()
        self._update_summary(mode, gear, pts, X, m, mag_L, mag_R, mag_z,
                             base_info, z_info, line1_x_abs)
