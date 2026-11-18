# KlinMeasurement

回转窑中心线（天宝全站仪）测量软件，面向 Windows 桌面环境。程序使用 Tkinter 提供图形界面，用于读取测量点数据、拟合截面圆心并分析一档、二档、三档圆心的共线偏差。

## 功能

- 读取 `xlsx`、`xls` 和 `csv` 截面点数据，拟合截面圆心。
- 计算中间截面相对首尾截面连线的 X/Z 偏差。
- 查看中心线分析图和拟合结果，并导出 Excel/CSV。
- 将文本测量数据转换为 Excel 表格。
- 导入棱镜坐标，进行托轮位置分析和可视化。
- 扫描、连接串口并按测量位置保存采集数据。

## 环境要求

- Windows
- Python 3.10 或更高版本
- 可用的 Tkinter（Windows 官方 Python 安装通常已包含）

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 运行

```powershell
python .\KlinMeasurement.py
```

主界面支持选择三档测量文件。每个数据文件至少应包含 X、Y、Z 三列；坐标按米读取后转换为毫米。Excel 导入和 Excel 导出需要 `openpyxl`。

## 打包

安装 PyInstaller 后，可使用项目中的打包命令：

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name KlinMeasurement --collect-all matplotlib .\KlinMeasurement.py
```

生成的可执行文件位于 `dist\KlinMeasurement.exe`。`build\` 和 `dist\` 均为本地构建产物，不纳入版本控制。

## 项目结构

| 文件 | 说明 |
| --- | --- |
| `KlinMeasurement.py` | 主窗口和中心线分析流程 |
| `analysis.py` | 点云读取、圆拟合和偏差计算 |
| `serial_acquisition.py` | 串口采集图形界面 |
| `serial_service.py` | 串口连接及后台接收服务 |
| `turret_position.py` | 托轮位置分析界面 |
| `turret_io.py` | 棱镜坐标文件解析 |
| `txt2xlsx.py` | 文本数据转 Excel |
| `KlinMeasurement.spec` | PyInstaller 打包配置 |

## 说明

本项目当前未附带测量数据样例。请勿将包含现场测量信息的原始数据或导出结果提交到公共仓库。
