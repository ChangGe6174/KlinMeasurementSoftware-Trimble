import re
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd

def extract_data_from_file(file_path):
    """从文件中提取38=、37=、39=后的数据"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"路径指向的不是文件: {file_path}")

    data = []
    current_record = {}

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                if line.startswith('>'):
                    if current_record:
                        data.append([current_record.get('38'),
                                     current_record.get('37'),
                                     current_record.get('39')])
                        current_record = {}
                    continue

                for tag in ['38', '37', '39']:
                    match = re.search(rf'{tag}=([^=\s]+)', line)
                    if match:
                        current_record[tag] = match.group(1)

        if current_record:
            data.append([current_record.get('38'),
                         current_record.get('37'),
                         current_record.get('39')])

        return data

    except PermissionError:
        raise PermissionError(f"没有权限访问文件: {file_path}")
    except Exception as e:
        raise Exception(f"读取文件时发生错误: {e}")

def create_xlsx(data, output_file):
    """创建xlsx文件"""
    df = pd.DataFrame(data)
    try:
        df.to_excel(output_file, index=False, header=False)
        print(f"数据已成功导出到 {output_file}")
    except PermissionError:
        raise PermissionError(f"没有权限写入文件: {output_file}")
    except Exception as e:
        raise Exception(f"写入文件时发生错误: {e}")

def convert_selected_files(parent=None):
    """选择并转换 1 到 10 个 txt 文件。"""
    file_paths = filedialog.askopenfilenames(
        parent=parent,
        title="选择1到10个txt文件",
        filetypes=[("Text files", "*.txt")],
    )

    if not (1 <= len(file_paths) <= 10):
        if file_paths:
            messagebox.showwarning("选择文件", "请选择1到10个txt文件。", parent=parent)
        return

    converted_files = []
    errors = []
    for file_path in file_paths:
        try:
            data = extract_data_from_file(file_path)
            file_dir = os.path.dirname(file_path)
            file_name = os.path.basename(file_path).replace('.txt', '.xlsx')
            output_file = os.path.join(file_dir, file_name)
            create_xlsx(data, output_file)
            converted_files.append(output_file)
        except PermissionError as e:
            errors.append(f"权限错误: {e}")
        except Exception as e:
            errors.append(f"发生错误: {e}")

    if errors:
        messagebox.showerror(
            "转换完成但有错误",
            "\n".join(errors),
            parent=parent,
        )
    elif converted_files:
        messagebox.showinfo(
            "转换完成",
            f"已转换 {len(converted_files)} 个文件，输出文件已保存到原 txt 文件所在目录。",
            parent=parent,
        )


def main():
    """主函数"""
    root = tk.Tk()
    root.withdraw()
    convert_selected_files(root)
    root.destroy()

if __name__ == "__main__":
    main()