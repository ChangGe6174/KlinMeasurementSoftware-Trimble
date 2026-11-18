# -*- coding: utf-8 -*-
"""串口助手及串口数据采集子模块。"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from serial_service import SerialService
except Exception:
    SerialService = None


CENTER_CODES = [
    ("一档左", "1L"), ("一档右", "1R"), ("一档下", "1D"),
    ("二档左", "2L"), ("二档右", "2R"), ("二档下", "2D"),
    ("三档左", "3L"), ("三档右", "3R"), ("三档下", "3D"),
]
TURRET_CODES = [
    ("一档左高", "1LU"), ("一档左低", "1LD"), ("一档右高", "1RU"), ("一档右低", "1RD"),
    ("二档左高", "2LU"), ("二档左低", "2LD"), ("二档右高", "2RU"), ("二档右低", "2RD"),
    ("三档左高", "3LU"), ("三档左低", "3LD"), ("三档右高", "3RU"), ("三档右低", "3RD"),
]


class ProjectDialog(tk.Toplevel):
    def __init__(self, master, on_project_selected):
        super().__init__(master)
        self.title("新建串口采集工程")
        self.geometry("620x180")
        self.transient(master)
        self.grab_set()
        self.on_project_selected = on_project_selected
        self.project_name = tk.StringVar(value="串口采集工程")
        self.parent_folder = tk.StringVar()
        self.result = None

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="工程名称").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=self.project_name).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(frame, text="上级文件夹").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=self.parent_folder).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="浏览...", command=self._browse_parent).grid(row=1, column=2)
        frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(buttons, text="新建工程", command=self._create).pack(side="left", padx=6)
        ttk.Button(buttons, text="打开现有工程", command=self._open_existing).pack(side="left", padx=6)
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="left", padx=6)

    def _browse_parent(self):
        folder = filedialog.askdirectory(title="选择工程上级文件夹", parent=self)
        if folder:
            self.parent_folder.set(folder)

    def _create(self):
        name = self.project_name.get().strip()
        parent = self.parent_folder.get().strip()
        if not name:
            messagebox.showwarning("工程名称为空", "请输入工程名称", parent=self)
            return
        if not parent:
            messagebox.showwarning("未选择文件夹", "请选择工程上级文件夹", parent=self)
            return
        root = os.path.join(parent, name)
        self._finish(root)

    def _open_existing(self):
        root = filedialog.askdirectory(title="选择现有工程文件夹", parent=self)
        if root:
            self._finish(root)

    def _finish(self, root):
        try:
            os.makedirs(os.path.join(root, "中心线"), exist_ok=True)
            os.makedirs(os.path.join(root, "托轮位置"), exist_ok=True)
        except Exception as exc:
            messagebox.showerror("创建工程失败", str(exc), parent=self)
            return
        self.result = root
        self.on_project_selected(root)
        self.destroy()


class SerialAcquisitionWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("串口数据采集")
        self.geometry("1180x760")
        self.project_root = None
        self.active_capture_code = None
        self.active_capture_name = None
        self.capture_prefix = ""
        self.rx_queue = queue.Queue()
        self.serial_service = None
        self.capture_buttons = {}
        self.active_capture_button = None

        self.project_name_var = tk.StringVar(value="未创建工程")
        self.project_path_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="串口未连接")
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="9600")
        self.bytesize_var = tk.StringVar(value="8")
        self.parity_var = tk.StringVar(value="None")
        self.stopbits_var = tk.StringVar(value="1")
        self.dtr_var = tk.BooleanVar(value=True)
        self.rts_var = tk.BooleanVar(value=True)
        self.rtscts_var = tk.BooleanVar(value=False)
        self.dsrdtr_var = tk.BooleanVar(value=False)
        self.xonxoff_var = tk.BooleanVar(value=False)
        self.encoding_var = tk.StringVar(value="utf-8")

        self._build_ui()
        self._refresh_ports()
        self.after(100, self._drain_rx_queue)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(150, self._open_project_dialog)

    def _build_ui(self):
        style = ttk.Style(self)
        style.configure("Capture.TButton", padding=(6, 8))
        style.configure(
            "CaptureActive.TButton",
            foreground="#FFFFFF",
            background="#1976D2",
            padding=(6, 8),
        )
        style.map(
            "CaptureActive.TButton",
            background=[("active", "#1565C0"), ("pressed", "#0D47A1")],
            foreground=[("active", "#FFFFFF")],
        )

        top = ttk.LabelFrame(self, text="工程与串口", padding=8)
        top.pack(fill="x", padx=8, pady=(8, 4))

        project_row = ttk.Frame(top)
        project_row.pack(fill="x")
        ttk.Label(project_row, text="项目名称:").pack(side="left")
        ttk.Entry(project_row, textvariable=self.project_name_var, width=24, state="readonly").pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(project_row, text="项目地址:").pack(side="left")
        ttk.Entry(project_row, textvariable=self.project_path_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(4, 8)
        )
        ttk.Button(project_row, text="新建工程", command=self._open_project_dialog).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(project_row, text="打开项目文件夹", command=self._open_project_folder).pack(side="left")

        serial_row = ttk.Frame(top)
        serial_row.pack(fill="x", pady=(8, 0))
        ttk.Label(serial_row, text="串口").pack(side="left")
        self.port_combo = ttk.Combobox(serial_row, textvariable=self.port_var, width=18, state="readonly")
        self.port_combo.pack(side="left", padx=(4, 8))
        ttk.Button(serial_row, text="扫描", command=self._refresh_ports).pack(side="left", padx=(0, 8))
        ttk.Label(serial_row, text="波特率").pack(side="left")
        ttk.Combobox(
            serial_row, textvariable=self.baud_var, width=8,
            values=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400"],
        ).pack(side="left", padx=(4, 8))
        ttk.Label(serial_row, text="数据位").pack(side="left")
        ttk.Combobox(serial_row, textvariable=self.bytesize_var, width=5, values=["5", "6", "7", "8"], state="readonly").pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(serial_row, text="校验位").pack(side="left")
        ttk.Combobox(
            serial_row, textvariable=self.parity_var, width=8,
            values=["None", "Even", "Odd", "Mark", "Space"], state="readonly",
        ).pack(side="left", padx=(4, 8))
        ttk.Label(serial_row, text="停止位").pack(side="left")
        ttk.Combobox(serial_row, textvariable=self.stopbits_var, width=5, values=["1", "1.5", "2"], state="readonly").pack(
            side="left", padx=(4, 8)
        )
        ttk.Checkbutton(serial_row, text="DTR", variable=self.dtr_var).pack(side="left", padx=4)
        ttk.Checkbutton(serial_row, text="RTS", variable=self.rts_var).pack(side="left", padx=4)
        ttk.Checkbutton(serial_row, text="硬件流控 RTS/CTS", variable=self.rtscts_var).pack(side="left", padx=4)
        ttk.Checkbutton(serial_row, text="DSR/DTR", variable=self.dsrdtr_var).pack(side="left", padx=4)
        ttk.Checkbutton(serial_row, text="软件流控 XON/XOFF", variable=self.xonxoff_var).pack(side="left", padx=4)
        self.connect_button = ttk.Button(serial_row, text="连接串口", command=self._toggle_serial)
        self.connect_button.pack(side="left", padx=(8, 8))
        self.serial_indicator = tk.Canvas(
            serial_row,
            width=16,
            height=16,
            highlightthickness=0,
        )
        self.serial_indicator.pack(side="left", padx=(4, 4))
        self.serial_indicator_id = self.serial_indicator.create_oval(2, 2, 14, 14, fill="#DC3545", outline="")
        ttk.Label(serial_row, textvariable=self.status_var, foreground="#666666").pack(side="left")

        modem_row = ttk.Frame(top)
        modem_row.pack(fill="x", pady=(6, 0))
        ttk.Label(modem_row, text="调制解调器状态:").pack(side="left")
        self.modem_status_var = tk.StringVar(value="DTR -  RTS -  DSR -  CTS -  DCD -  RI -")
        ttk.Label(modem_row, textvariable=self.modem_status_var).pack(side="left", padx=(6, 0))
        self.after(500, self._update_modem_status)

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(body)
        body.add(left, weight=1)
        center = ttk.LabelFrame(left, text="中心线位置", padding=6)
        center.pack(fill="x")
        self._build_position_grid(center, CENTER_CODES, "中心线")
        turret = ttk.LabelFrame(left, text="托轮位置", padding=6)
        turret.pack(fill="x", pady=(8, 0))
        self._build_position_grid(turret, TURRET_CODES, "托轮位置", columns=4)

        right = ttk.LabelFrame(body, text="串口内容", padding=6)
        body.add(right, weight=2)
        codec_row = ttk.Frame(right)
        codec_row.pack(fill="x")
        ttk.Label(codec_row, text="文本编码").pack(side="left")
        ttk.Combobox(
            codec_row, textvariable=self.encoding_var, width=10,
            values=["utf-8", "gbk", "gb2312", "ascii", "latin-1"], state="readonly",
        ).pack(side="left", padx=(4, 12))
        ttk.Label(codec_row, text="采集位置:").pack(side="left")
        self.capture_label = ttk.Label(codec_row, text="未选择", foreground="#444444")
        self.capture_label.pack(side="left", padx=4)

        self.rx_text = tk.Text(right, wrap="none", font=("Consolas", 10))
        text_scroll_y = ttk.Scrollbar(right, orient="vertical", command=self.rx_text.yview)
        text_scroll_x = ttk.Scrollbar(right, orient="horizontal", command=self.rx_text.xview)
        self.rx_text.configure(yscrollcommand=text_scroll_y.set, xscrollcommand=text_scroll_x.set)
        self.rx_text.pack(side="top", fill="both", expand=True)
        text_scroll_y.pack(side="right", fill="y")
        text_scroll_x.pack(side="bottom", fill="x")

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="清空串口缓存", command=self._clear_receive).pack(side="left")
        ttk.Button(actions, text="清空显示", command=self._clear_display).pack(side="left", padx=6)
        ttk.Button(actions, text="保存数据", command=self._save_data).pack(side="left")

    def _build_position_grid(self, parent, entries, folder_name, columns=3):
        for index, (name, code) in enumerate(entries):
            row, col = divmod(index, columns)
            button = tk.Button(
                parent,
                text=f"{name}\n{code}",
                width=14,
                relief="raised",
                bg="#F0F0F0",
                activebackground="#D6E8F7",
                command=lambda n=name, c=code, f=folder_name: self._start_capture(n, c, f),
            )
            button.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            self.capture_buttons[(folder_name, code)] = button
        for col in range(columns):
            parent.columnconfigure(col, weight=1)

    def _open_project_dialog(self):
        ProjectDialog(self, self._set_project)

    def _set_project(self, root):
        self.project_root = root
        self.project_name_var.set(os.path.basename(root))
        self.project_path_var.set(root)

    def _set_serial_indicator(self, connected: bool):
        color = "#1976D2" if connected else "#DC3545"
        if hasattr(self, "serial_indicator") and hasattr(self, "serial_indicator_id"):
            self.serial_indicator.itemconfigure(self.serial_indicator_id, fill=color)

    def _update_modem_status(self):
        if self.serial_service is not None:
            try:
                status = self.serial_service.get_modem_status()
                self.modem_status_var.set(
                    "  ".join(
                        f"{name} {'开' if value else '关'}"
                        for name, value in status.items()
                    )
                )
            except Exception:
                pass
        self.after(500, self._update_modem_status)

    def _refresh_ports(self):
        if SerialService is None:
            self.status_var.set("缺少 pyserial")
            return
        ports = SerialService.list_ports()
        self.port_combo["values"] = ports
        if ports:
            if self.port_var.get() not in ports:
                self.port_var.set(ports[0])
        else:
            self.port_var.set("")

    def _toggle_serial(self):
        if SerialService is None:
            messagebox.showerror("缺少依赖", "请安装 pyserial：pip install pyserial")
            self._set_serial_indicator(False)
            return
        if self.serial_service is not None and self.serial_service.is_connected:
            self.serial_service.disconnect()
            self.serial_service = None
            self.connect_button.configure(text="连接串口")
            self._set_serial_indicator(False)
            self.status_var.set("串口未连接")
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("未选择串口", "请先扫描并选择可用串口")
            self._set_serial_indicator(False)
            return
        parity_map = {"None": "N", "Even": "E", "Odd": "O", "Mark": "M", "Space": "S"}
        try:
            baud = int(self.baud_var.get())
            bytesize = int(self.bytesize_var.get())
            stopbits = float(self.stopbits_var.get())
            self.serial_service = SerialService(self._queue_rx, self._queue_error)
            self.serial_service.connect(
                port, baud, bytesize, parity_map[self.parity_var.get()],
                stopbits, self.dtr_var.get(), self.rts_var.get(),
                rtscts=self.rtscts_var.get(),
                dsrdtr=self.dsrdtr_var.get(),
                xonxoff=self.xonxoff_var.get(),
            )
            self.connect_button.configure(text="断开串口")
            self._set_serial_indicator(True)
            self.status_var.set(f"已连接 {port}")
        except Exception as exc:
            self.serial_service = None
            messagebox.showerror("串口连接失败", str(exc))
            self._set_serial_indicator(False)
            self.status_var.set("串口未连接")

    def _queue_rx(self, data):
        self.rx_queue.put(("data", data))

    def _queue_error(self, message):
        self.rx_queue.put(("error", message))

    def _drain_rx_queue(self):
        while True:
            try:
                kind, value = self.rx_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "error":
                self.status_var.set("串口读取错误")
                self._set_serial_indicator(False)
                messagebox.showerror("串口读取错误", str(value))
            else:
                encoding = self.encoding_var.get()
                if encoding == "ascii":
                    text = value.decode("ascii", errors="replace")
                else:
                    try:
                        text = value.decode(encoding)
                    except Exception:
                        text = value.decode("utf-8", errors="replace")
                self.rx_text.insert("end", text)
                self.rx_text.see("end")
        self.after(100, self._drain_rx_queue)

    def _start_capture(self, name, code, folder_name):
        if not self.project_root:
            messagebox.showwarning("未选择工程", "请先新建或打开工程")
            return
        if self.serial_service is None or not self.serial_service.is_connected:
            messagebox.showwarning("串口未连接", "请先连接串口")
            return
        if self.active_capture_button is not None:
            try:
                self.active_capture_button.configure(bg="#F0F0F0", fg="#000000", activebackground="#D6E8F7")
            except tk.TclError:
                pass
        selected_button = self.capture_buttons.get((folder_name, code))
        if selected_button is not None:
            selected_button.configure(bg="#1976D2", fg="#FFFFFF", activebackground="#1565C0")
            self.active_capture_button = selected_button
        self.serial_service.clear_receive_buffer()
        self.rx_text.delete("1.0", "end")
        self.active_capture_code = code
        self.active_capture_name = name
        self.capture_prefix = folder_name
        self.capture_label.configure(text=f"{name} ({code})")
        self.status_var.set(f"正在采集：{name} ({code})")

    def _clear_receive(self):
        if self.serial_service is not None:
            self.serial_service.clear_receive_buffer()
        self.rx_text.delete("1.0", "end")
        self.status_var.set("已清空串口缓存" if self.status_var.get().startswith("已连接") else self.status_var.get())

    def _clear_display(self):
        self.rx_text.delete("1.0", "end")

    def _next_filename(self, folder, code):
        existing = []
        pattern = re.compile(rf"^{re.escape(code)}-(\d+)\.txt$")
        for filename in os.listdir(folder):
            match = pattern.match(filename)
            if match:
                existing.append(int(match.group(1)))
        suffix = max(existing, default=0) + 1
        return os.path.join(folder, f"{code}-{suffix}.txt")

    def _save_data(self):
        if not self.project_root:
            messagebox.showwarning("未选择工程", "请先新建或打开工程")
            return
        content = self.rx_text.get("1.0", "end-1c")
        if not content:
            messagebox.showwarning("没有数据", "串口内容为空")
            return
        if self.active_capture_code:
            folder_name = "中心线" if self.capture_prefix == "中心线" else "托轮位置"
            folder = os.path.join(self.project_root, folder_name)
            os.makedirs(folder, exist_ok=True)
            save_path = self._next_filename(folder, self.active_capture_code)
        else:
            save_path = filedialog.asksaveasfilename(
                title="保存串口数据",
                initialdir=self.project_root,
                defaultextension=".txt",
                filetypes=[("Text", "*.txt")],
                parent=self,
            )
            if not save_path:
                return
        try:
            with open(save_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            messagebox.showinfo("保存成功", f"数据已保存到:\n{save_path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _open_project_folder(self):
        if not self.project_root:
            messagebox.showwarning("未选择工程", "请先新建或打开工程")
            return
        os.startfile(self.project_root)

    def _close(self):
        if self.serial_service is not None:
            self.serial_service.disconnect()
        self.destroy()
