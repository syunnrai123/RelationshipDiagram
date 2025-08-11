import pymysql
import sv_ttk
from graphviz import Digraph
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import os
import threading
import webbrowser
import json
import sys

# --- 全局配置文件名 ---
CONFIG_FILE = "relationship_diagram_config.json"


# --- 辅助类：鼠标悬停提示 (不变) ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, background="#FFFFE0", relief="solid", borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tooltip: self.tooltip.destroy()
        self.tooltip = None


# --- 主应用 ---
class UltimateBeautifiedApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("数据库关系图生成器 - 终极美化版 💎")
        self.geometry("700x750")

        # ... (数据模型和UI创建逻辑与上一版相同) ...
        # --- 数据模型 ---
        self.db_entries = {}
        self.output_path = tk.StringVar()
        self.last_generated_file = None
        self.graph_style = {
            'layout': tk.StringVar(), 'spline': tk.StringVar(), 'bg_color': tk.StringVar(),
            'node_color_default': tk.StringVar(), 'node_color_start': tk.StringVar(),
            'node_color_link': tk.StringVar(), 'node_color_end': tk.StringVar(),
        }
        # --- 创建UI并加载配置 ---
        sv_ttk.set_theme("light")
        self._create_widgets()
        self._load_config()
        # --- 绑定窗口关闭事件以保存配置 ---
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ... (除了 _render_graph 外，其他函数与上一版 StableApp 相同, 此处为简洁省略) ...
    # --- 1. 配置持久化 (核心改进) ---
    def _load_config(self):
        self._log("正在加载配置...", "INFO")
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)

            # 加载数据库连接信息 (密码除外)
            db_conf = config.get("database", {})
            for key, entry in self.db_entries.items():
                if key != "密码":
                    entry.delete(0, tk.END)
                    entry.insert(0, db_conf.get(key, ''))

            # 加载路径和样式
            self.output_path.set(config.get("output_path", os.getcwd()))
            style_conf = config.get("graph_style", {})
            for key, var in self.graph_style.items():
                var.set(style_conf.get(key, self._get_default_styles()[key]))

            self._log("✅ 配置加载成功!", "SUCCESS")
        except (FileNotFoundError, json.JSONDecodeError):
            self._log("未找到或配置文件无效，使用默认设置。", "INFO")
            # 文件不存在或损坏时，加载默认值
            self.output_path.set(os.getcwd())
            default_styles = self._get_default_styles()
            for key, var in self.graph_style.items():
                var.set(default_styles[key])

    def _save_config(self):
        self._log("正在保存配置...", "INFO")
        db_conf = {key: entry.get() for key, entry in self.db_entries.items() if key != "密码"}

        config = {
            "database": db_conf,
            "output_path": self.output_path.get(),
            "graph_style": {key: var.get() for key, var in self.graph_style.items()},
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        self._log("✅ 配置已保存。", "SUCCESS")

    def _on_closing(self):
        self._save_config()
        self.destroy()

    def _get_default_styles(self):
        return {
            'layout': 'TB', 'spline': 'ortho', 'bg_color': '#FAFAFA',
            'node_color_default': '#87CEEB', 'node_color_start': '#FFDDC1',
            'node_color_link': '#D1FFBD', 'node_color_end': '#E0BBE4',
        }

    # --- 2. UI创建 (与之前版本类似，但逻辑更清晰) ---
    def _create_widgets(self):
        # ... 此部分UI代码与上版基本一致，为保证完整性，此处保留 ...
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        main_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text=' 🚀 生成器 ')
        notebook.add(settings_tab, text=' 🎨 样式设置 ')
        self._create_main_tab(main_tab)
        self._create_settings_tab(settings_tab)

    def _create_main_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        conn_frame = ttk.LabelFrame(parent, text=" 🗄️ 数据库连接信息 ")
        conn_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        conn_frame.columnconfigure(1, weight=1)
        labels = ["主机:", "端口:", "用户名:", "密码:", "数据库:"]
        for i, label in enumerate(labels):
            ttk.Label(conn_frame, text=label).grid(row=i, column=0, padx=10, pady=8, sticky="w")
            entry = ttk.Entry(conn_frame, show="*" if "密码" in label else "")
            entry.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
            self.db_entries[label.strip(':')] = entry

        out_frame = ttk.LabelFrame(parent, text=" 📁 输出路径 ")
        out_frame.grid(row=1, column=0, padx=5, pady=10, sticky="ew")
        out_frame.columnconfigure(0, weight=1)
        path_entry = ttk.Entry(out_frame, textvariable=self.output_path, state="readonly")
        path_entry.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        browse_btn = ttk.Button(out_frame, text="浏览...", command=self._browse_directory)
        browse_btn.grid(row=0, column=1, padx=10, pady=8)

        action_frame = ttk.Frame(parent)
        action_frame.grid(row=2, column=0, pady=10, sticky="ew")
        action_frame.columnconfigure((0, 1, 2), weight=1)
        self.test_btn = ttk.Button(action_frame, text="✔️ 测试连接", command=self._test_connection,
                                   style="Accent.TButton")
        self.fk_btn = ttk.Button(action_frame, text="🔗 基于外键生成",
                                 command=lambda: self._run_generation(self._execute_generate_by_fk))
        self.infer_btn = ttk.Button(action_frame, text="💡 基于约定推断",
                                    command=lambda: self._run_generation(self._execute_generate_by_inference))
        self.test_btn.grid(row=0, column=0, padx=5, ipady=5, sticky="ew")
        self.fk_btn.grid(row=0, column=1, padx=5, ipady=5, sticky="ew")
        self.infer_btn.grid(row=0, column=2, padx=5, ipady=5, sticky="ew")

        log_frame = ttk.LabelFrame(parent, text=" 📈 状态日志 ")
        log_frame.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")
        parent.rowconfigure(3, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        self.progress_bar = ttk.Progressbar(log_frame, mode='indeterminate')
        self.progress_bar.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word", relief="flat", borderwidth=0)
        self.log_text.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.log_text.tag_config("SUCCESS", foreground="green")
        self.log_text.tag_config("ERROR", foreground="red")
        self.log_text.tag_config("INFO", foreground="blue")
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=1, padx=5, pady=5, sticky="ns")
        self.clear_log_btn = ttk.Button(log_btn_frame, text="清空", command=self._clear_log)
        self.open_file_btn = ttk.Button(log_btn_frame, text="打开图片", state="disabled", command=self._open_last_file)
        self.clear_log_btn.pack(pady=5, fill="x")
        self.open_file_btn.pack(pady=5, fill="x")

    def _create_settings_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        theme_frame = ttk.LabelFrame(parent, text=" 🎨 应用主题 ")
        theme_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        theme_switch = ttk.Checkbutton(theme_frame, text="切换为暗黑模式", style="Switch.TCheckbutton",
                                       command=lambda: sv_ttk.set_theme(
                                           "dark" if theme_switch.instate(['selected']) else "light"))
        theme_switch.pack(padx=10, pady=10)

        style_frame = ttk.LabelFrame(parent, text=" 🖌️ 图表样式配置 ")
        style_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        style_frame.columnconfigure(1, weight=1)

        ttk.Label(style_frame, text="布局方向:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ttk.OptionMenu(style_frame, self.graph_style['layout'], 'TB', 'TB', 'LR').grid(row=0, column=1, padx=10, pady=8,
                                                                                       sticky="w")

        ttk.Label(style_frame, text="连线样式:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        ttk.OptionMenu(style_frame, self.graph_style['spline'], 'ortho', 'ortho', 'curved', 'spline').grid(row=1,
                                                                                                           column=1,
                                                                                                           padx=10,
                                                                                                           pady=8,
                                                                                                           sticky="w")

        colors_map = [("背景色", 'bg_color'), ("默认节点色", 'node_color_default'), ("起始节点色", 'node_color_start'),
                      ("中间节点色", 'node_color_link'), ("末端节点色", 'node_color_end')]
        for i, (text, key) in enumerate(colors_map, 2):
            ttk.Label(style_frame, text=f"{text}:").grid(row=i, column=0, padx=10, pady=5, sticky="w")
            color_btn = ttk.Button(style_frame, text="选择颜色", command=lambda k=key: self._choose_color(k))
            color_btn.grid(row=i, column=2, padx=10, pady=5)
            color_preview = tk.Label(style_frame, textvariable=self.graph_style[key], relief="sunken", width=10)
            color_preview.grid(row=i, column=1, padx=10, pady=5, sticky="w")
            # 使用 trace_add 的 'write' 回调来动态更新背景色
            self.graph_style[key].trace_add("write", lambda name, index, mode, var=self.graph_style[key],
                                                            label=color_preview: label.config(bg=var.get()))

    # --- 3. 核心逻辑 (重构线程和UI交互) ---
    def _choose_color(self, key):
        color_code = colorchooser.askcolor(title="选择颜色", initialcolor=self.graph_style[key].get())
        if color_code[1]: self.graph_style[key].set(color_code[1])

    def _log(self, msg, level="INFO"):
        self.after(0, self.__update_log, msg, level)

    def __update_log(self, msg, level):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{level}] {msg}\n", level)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def _open_last_file(self):
        if self.last_generated_file and os.path.exists(self.last_generated_file):
            webbrowser.open(self.last_generated_file)
        else:
            messagebox.showwarning("警告", "找不到上次生成的文件。")

    def _browse_directory(self):
        path = filedialog.askdirectory(initialdir=self.output_path.get())
        if path: self.output_path.set(path); self._log(f"输出路径已更新: {path}", "INFO")

    def _toggle_controls(self, state="normal"):
        self.after(0, self.__update_controls_state, state)

    def __update_controls_state(self, state):
        final_state = "normal" if state == "normal" else "disabled"
        if final_state == "disabled":
            self.progress_bar.start(10)
        else:
            self.progress_bar.stop()
        for btn in [self.test_btn, self.fk_btn, self.infer_btn]: btn.config(state=final_state)

    def _run_threaded(self, target_func):
        self._toggle_controls("disabled")
        thread = threading.Thread(target=target_func, daemon=True)
        thread.start()

    def _get_db_connection(self):
        details = {k: v.get() for k, v in self.db_entries.items()}
        return pymysql.connect(
            host=details['主机'], port=int(details['端口']), user=details['用户名'],
            password=details['密码'], database=details['数据库'], cursorclass=pymysql.cursors.DictCursor
        )

    # --- 测试连接 ---
    def _test_connection(self):
        self._run_threaded(self._execute_test_connection)

    def _execute_test_connection(self):
        try:
            self._log("正在连接...", "INFO")
            conn = self._get_db_connection()
            conn.close()
            self._log("连接成功！", "SUCCESS")
            self.after(0, lambda: messagebox.showinfo("成功", "数据库连接成功！"))
        except Exception as e:
            self._log(f"连接失败: {e}", "ERROR")
            self.after(0, lambda: messagebox.showerror("错误", f"连接失败:\n{e}"))
        finally:
            self._toggle_controls("normal")

    # --- 生成图表 (主功能修复) ---
    def _run_generation(self, generation_method):
        self._run_threaded(generation_method)

    def _execute_generate_by_fk(self):
        try:
            self._log("--- 开始基于外键生成 ---", "INFO")
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name, referenced_table_name FROM information_schema.KEY_COLUMN_USAGE WHERE table_schema = %s AND referenced_table_name IS NOT NULL",
                    (self.db_entries['数据库'].get(),))
                relations = {(row['table_name'], row['referenced_table_name']) for row in cur.fetchall()}
            conn.close()
            self._render_graph(relations, 'fk', f"{self.db_entries['数据库'].get()} Schema (FK Based)")
        except Exception as e:
            self._log(f"生成失败: {e}", "ERROR")
            self.after(0, lambda: messagebox.showerror("错误", f"生成失败:\n{e}"))
        finally:
            self._toggle_controls("normal")

    def _execute_generate_by_inference(self):
        try:
            self._log("--- 开始基于约定推断 ---", "INFO")
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_KEY FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s",
                    (self.db_entries['数据库'].get(),))
                cols = cur.fetchall()
            conn.close()

            tables = {}
            for col in cols:
                tbl = col['TABLE_NAME'];
                info = tables.setdefault(tbl, {'cols': [], 'pk': None})
                info['cols'].append(col['COLUMN_NAME'])
                if col['COLUMN_KEY'] == 'PRI': info['pk'] = col['COLUMN_NAME']

            relations = set()
            for t_name, info in tables.items():
                for c_name in info['cols']:
                    if c_name.endswith('_id') and c_name != info.get('pk'):
                        prefix = c_name[:-3]
                        for target in tables:
                            if target.rstrip('s') == prefix and tables.get(target, {}).get('pk') == 'id':
                                relations.add((t_name, target));
                                break
            self._render_graph(relations, 'inferred', f"{self.db_entries['数据库'].get()} Schema (Inferred)")
        except Exception as e:
            self._log(f"推断失败: {e}", "ERROR")
            self.after(0, lambda: messagebox.showerror("错误", f"推断失败:\n{e}"))
        finally:
            self._toggle_controls("normal")

    # --- 渲染引擎 (核心优化) ---
    def _render_graph(self, relations, suffix, label):
        if not relations:
            self._log("未找到任何关系，任务中止。", "ERROR")
            self.after(0, lambda: messagebox.showwarning("提示", "未能找到任何表间关系。"))
            return

        self._log("开始渲染美化版图表...", "INFO")
        s = self.graph_style

        # 1. 定义整体图表属性 (增加间距)
        graph_attrs = {
            'rankdir': s['layout'].get(),
            'bgcolor': s['bg_color'].get(),
            'pad': '1.0',  # 增加图表整体内边距
            'splines': s['spline'].get(),
            'nodesep': '0.8',  # 节点间最小距离
            'ranksep': '1.2',  # 层级间最小距离 (关键)
            'label': f"\n{label}",  # 标题前加换行符，增加与顶部的距离
            'fontsize': '22',
            'fontname': 'Segoe UI,Verdana,Arial',  # 优先使用更清晰的字体
            'fontcolor': '#333333',
            'overlap': 'false'  # 禁止节点重叠
        }

        # 2. 定义节点属性 (增加内部边距和边框)
        node_attrs = {
            'style': 'filled,rounded',
            'shape': 'box',
            'fontname': 'Segoe UI,Verdana,Arial',
            'fontsize': '14',  # 增大字体
            'fontcolor': '#2D2D2D',  # 更深的字体颜色
            'margin': '0.4',  # 节点内部文字与边框的距离 (关键)
            'color': '#666666'  # 节点边框颜色
        }

        # 3. 定义边/连接线属性
        edge_attrs = {
            'color': '#757575',
            'arrowsize': '0.9',
            'penwidth': '1.5'  # 加粗线条
        }

        dot = Digraph(format="png", graph_attr=graph_attrs, node_attr=node_attrs, edge_attr=edge_attrs)

        all_nodes = set(sum(relations, ()));
        in_d, out_d = {n: 0 for n in all_nodes}, {n: 0 for n in all_nodes}
        for f, t in relations: out_d[f] += 1; in_d[t] += 1

        for node in all_nodes:
            color = s['node_color_default'].get()
            if out_d[node] > 0 and in_d[node] == 0:
                color = s['node_color_start'].get()
            elif out_d[node] > 0 and in_d[node] > 0:
                color = s['node_color_link'].get()
            elif out_d[node] == 0 and in_d[node] > 0:
                color = s['node_color_end'].get()
            dot.node(node, fillcolor=color)

        for f, t in relations: dot.edge(f, t)

        db_name = self.db_entries['数据库'].get() or "db"
        output_filename = os.path.join(self.output_path.get(), f"relation_{db_name}_{suffix}")

        try:
            generated_path = dot.render(output_filename, cleanup=True, view=False)
            self.last_generated_file = generated_path
            self._log(f"图表已生成: {generated_path}", "SUCCESS")
            self.after(0, lambda: self.open_file_btn.config(state="normal"))
            self.after(0, lambda: messagebox.showinfo("完成", f"图表已成功生成！\n路径: {generated_path}"))
        except Exception as e:
            self._log(f"Graphviz渲染失败: {e}", "ERROR")
            self.after(0, lambda: messagebox.showerror("渲染错误",
                                                       f"无法调用Graphviz生成图片，请确保它已安装并添加到系统PATH环境变量。\n\n错误: {e}"))


if __name__ == "__main__":
    app = UltimateBeautifiedApp()
    app.mainloop()