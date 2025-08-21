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

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


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
        self.title("数据库关系图生成器 Pro (最终稳定版)")
        self.geometry("1200x800")

        # --- 数据模型 ---
        self.db_entries = {}
        self.output_path = tk.StringVar()
        self.last_generated_file = None
        self.config_file_path = tk.StringVar()
        self.db_type = tk.StringVar(value="MySQL")

        self.db_search_var = tk.StringVar()
        self.table_search_var = tk.StringVar()
        self.db_listbox = None
        self.table_listbox = None
        self.full_db_list = []
        self.full_table_list = []

        self.db_dialect_map = {"MySQL": "mysql+pymysql", "PostgreSQL": "postgresql+psycopg2", "SQLite": "sqlite"}
        self.graph_style = {'layout': tk.StringVar(), 'spline': tk.StringVar(), 'bg_color': tk.StringVar(),
                            'node_color_default': tk.StringVar(), 'node_color_start': tk.StringVar(),
                            'node_color_link': tk.StringVar(), 'node_color_end': tk.StringVar()}
        self.layout_map = {'从上到下 (TB)': 'TB', '从左到右 (LR)': 'LR'}
        self.spline_map = {'直角连线 (ortho)': 'ortho', '曲线 (curved)': 'curved', '样条曲线 (spline)': 'spline'}
        self.layout_map_rev = {v: k for k, v in self.layout_map.items()}
        self.spline_map_rev = {v: k for k, v in self.spline_map.items()}

        sv_ttk.set_theme("light")
        self._create_widgets()

        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))

        default_config_path = os.path.join(application_path, "relationship_diagram_config.json")
        self.config_file_path.set(default_config_path)
        self._load_config()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # --- 1. 配置持久化 (不变) ---
    def _load_config(self, filepath=None):
        target_path = filepath or self.config_file_path.get()
        self._log(f"正在从 {os.path.basename(target_path)} 加载配置...", "INFO")
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.config_file_path.set(target_path)
            self.db_type.set(config.get("db_type", "MySQL"))
            db_conf = config.get("database", {})
            for key, entry in self.db_entries.items():
                if key != "密码" and key in db_conf: entry.delete(0, tk.END); entry.insert(0, db_conf.get(key, ''))
            self.output_path.set(config.get("output_path", os.getcwd()))
            style_conf = config.get("graph_style", {})
            for key, var in self.graph_style.items(): var.set(style_conf.get(key, self._get_default_styles()[key]))
            self._log("✅ 配置加载成功!", "SUCCESS")
        except (FileNotFoundError, json.JSONDecodeError):
            self._log(f"未找到或配置文件无效，使用默认设置。", "INFO")
            if not filepath:
                self.output_path.set(os.getcwd());
                self.db_type.set("MySQL")
                default_styles = self._get_default_styles()
                for key, var in self.graph_style.items(): var.set(default_styles[key])
            else:
                self.after(0, lambda: messagebox.showwarning("加载失败", f"无法加载或解析文件：\n{target_path}"))
        self.after(0, self._update_ui_from_style_vars);
        self.after(0, self._on_db_type_changed)

    def _save_config(self, filepath=None):
        target_path = filepath or self.config_file_path.get()
        if not target_path: self._log("配置文件路径为空，无法保存。", "ERROR"); return
        self._log(f"正在保存配置到 {os.path.basename(target_path)}...", "INFO")
        db_conf = {key: entry.get() for key, entry in self.db_entries.items() if key != "密码"}
        config = {"db_type": self.db_type.get(), "database": db_conf, "output_path": self.output_path.get(),
                  "graph_style": {key: var.get() for key, var in self.graph_style.items()}}
        try:
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self.config_file_path.set(target_path);
            self._log("✅ 配置已保存。", "SUCCESS")
        except Exception as e:
            self._log(f"保存配置失败: {e}", "ERROR");
            self.after(0, lambda: messagebox.showerror("保存失败",
                                                       f"无法保存配置文件到：\n{target_path}\n\n错误: {e}"))

    def _select_and_load_config(self):
        path = filedialog.askopenfilename(title="选择配置文件",
                                          filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                                          initialdir=os.path.dirname(self.config_file_path.get()))
        if path: self._load_config(filepath=path)

    def _save_config_as(self):
        path = filedialog.asksaveasfilename(title="将配置另存为...",
                                            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                                            initialdir=os.path.dirname(self.config_file_path.get()),
                                            defaultextension=".json", initialfile="new_config.json")
        if path: self._save_config(filepath=path)

    def _on_closing(self):
        self._save_config();
        self.destroy()

    def _get_default_styles(self):
        return {'layout': 'TB', 'spline': 'ortho', 'bg_color': '#FAFAFA', 'node_color_default': '#87CEEB',
                'node_color_start': '#FFDDC1', 'node_color_link': '#D1FFBD', 'node_color_end': '#E0BBE4'}

    # --- 2. UI创建 (回归双栏布局) ---
    def _create_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        left_panel = ttk.Frame(main_pane, width=600)
        right_panel = ttk.Frame(main_pane, width=600)
        main_pane.add(left_panel, weight=1)
        main_pane.add(right_panel, weight=1)

        self._create_workflow_panel(left_panel)
        self._create_info_panel(right_panel)

    def _create_workflow_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        step1_frame = ttk.LabelFrame(parent, text=" ❶ 连接到数据库服务器 ")
        step1_frame.grid(row=0, column=0, padx=10, pady=(5, 10), sticky="ew")
        step1_frame.columnconfigure(1, weight=1)

        ttk.Label(step1_frame, text="数据库类型:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.db_type_combo = ttk.Combobox(step1_frame, textvariable=self.db_type, state="readonly",
                                          values=list(self.db_dialect_map.keys()))
        self.db_type_combo.grid(row=0, column=1, columnspan=2, padx=10, pady=8, sticky="w")
        self.db_type_combo.bind("<<ComboboxSelected>>", self._on_db_type_changed)

        labels = ["主机:", "端口:", "用户名:", "密码:"]
        self.db_entries['数据库'] = ttk.Entry(parent)
        for i, label_text in enumerate(labels, 1):
            key = label_text.strip(':');
            ttk.Label(step1_frame, text=label_text).grid(row=i, column=0, padx=10, pady=8, sticky="w")
            entry = ttk.Entry(step1_frame, show="*" if "密码" in label_text else "")
            entry.grid(row=i, column=1, columnspan=2, padx=10, pady=8, sticky="ew")
            self.db_entries[key] = entry;
            setattr(self, f"entry_{key}", entry)

        self.connect_btn = ttk.Button(step1_frame, text="🔗 连接并加载数据库", command=self._fetch_database_list,
                                      style="Accent.TButton")
        self.connect_btn.grid(row=len(labels) + 1, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        step2_frame = ttk.LabelFrame(parent, text=" ❷ 选择数据库和表 ")
        step2_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        step2_frame.columnconfigure(0, weight=1)
        step2_frame.rowconfigure(1, weight=1)
        step2_frame.rowconfigure(3, weight=2)

        db_area_frame = ttk.LabelFrame(step2_frame, text="数据库列表")
        db_area_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=5, sticky="nsew")
        db_area_frame.columnconfigure(0, weight=1)
        db_area_frame.rowconfigure(1, weight=1)

        db_search_frame = ttk.Frame(db_area_frame)
        db_search_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        db_search_frame.columnconfigure(1, weight=1)
        ttk.Label(db_search_frame, text="🔍 搜索:").grid(row=0, column=0, sticky="w")
        self.db_search_entry = ttk.Entry(db_search_frame, textvariable=self.db_search_var, state="disabled")
        self.db_search_entry.grid(row=0, column=1, padx=5, sticky="ew")
        self.db_search_var.trace_add("write", self._filter_db_list)

        self.db_listbox = tk.Listbox(db_area_frame, selectmode="single", relief="solid", borderwidth=1,
                                     state="disabled", exportselection=False, height=6)
        self.db_listbox.grid(row=1, column=0, padx=5, pady=(0, 5), sticky="nsew")
        db_scrollbar = ttk.Scrollbar(db_area_frame, orient="vertical", command=self.db_listbox.yview)
        db_scrollbar.grid(row=1, column=1, padx=(0, 5), pady=(0, 5), sticky="ns")
        self.db_listbox.config(yscrollcommand=db_scrollbar.set)
        self.db_listbox.bind("<<ListboxSelect>>", self._on_database_selected)

        self.fetch_tables_btn = ttk.Button(db_area_frame, text="⬇️ (刷新)获取选中库的表",
                                           command=self._on_fetch_tables_button_click, state="disabled")
        self.fetch_tables_btn.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        table_area_frame = ttk.LabelFrame(step2_frame, text="表列表")
        table_area_frame.grid(row=2, column=0, rowspan=2, padx=10, pady=5, sticky="nsew")
        table_area_frame.columnconfigure(0, weight=1)
        table_area_frame.rowconfigure(1, weight=1)

        table_search_frame = ttk.Frame(table_area_frame)
        table_search_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        table_search_frame.columnconfigure(1, weight=1)
        ttk.Label(table_search_frame, text="🔍 搜索:").grid(row=0, column=0, sticky="w")
        self.table_search_entry = ttk.Entry(table_search_frame, textvariable=self.table_search_var, state="disabled")
        self.table_search_entry.grid(row=0, column=1, padx=5, sticky="ew")
        self.table_search_var.trace_add("write", self._filter_table_list)

        self.table_listbox = tk.Listbox(table_area_frame, selectmode="extended", relief="solid", borderwidth=1,
                                        state="disabled", exportselection=False)
        self.table_listbox.grid(row=1, column=0, padx=5, pady=(0, 5), sticky="nsew")
        table_scrollbar = ttk.Scrollbar(table_area_frame, orient="vertical", command=self.table_listbox.yview)
        table_scrollbar.grid(row=1, column=1, padx=(0, 5), pady=(0, 5), sticky="ns")
        self.table_listbox.config(yscrollcommand=table_scrollbar.set)

        side_btn_frame = ttk.Frame(table_area_frame)
        side_btn_frame.grid(row=1, column=2, padx=(0, 5), pady=(0, 5), sticky="ns")
        ttk.Button(side_btn_frame, text="全选", command=self._select_all_tables).pack(side="top", pady=2, fill="x")
        ttk.Button(side_btn_frame, text="全不选", command=self._deselect_all_tables).pack(side="top", pady=2, fill="x")

    def _create_info_panel(self, parent):
        parent.rowconfigure(0, weight=1);
        parent.columnconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        log_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text=' ⚙️ 样式与配置 ')
        notebook.add(log_tab, text=' 📈 生成与日志 ')

        self._create_log_panel(log_tab)
        self._create_settings_panel(settings_tab)

    def _create_log_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        step3_frame = ttk.LabelFrame(parent, text=" ❸ 生成与输出 ")
        step3_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        step3_frame.columnconfigure(0, weight=1)

        ttk.Label(step3_frame, text="输出路径:").grid(row=0, column=0, columnspan=2, padx=10, pady=(8, 0), sticky="w")
        path_entry = ttk.Entry(step3_frame, textvariable=self.output_path, state="readonly")
        path_entry.grid(row=1, column=0, padx=10, pady=(2, 8), sticky="ew")
        browse_btn = ttk.Button(step3_frame, text="...", command=self._browse_directory, width=4)
        browse_btn.grid(row=1, column=1, padx=(0, 10), pady=(2, 8))

        action_frame = ttk.Frame(step3_frame);
        action_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        action_frame.columnconfigure((0, 1), weight=1)
        self.fk_btn = ttk.Button(action_frame, text="从外键生成",
                                 command=lambda: self._run_generation(self._execute_generate_by_fk), state="disabled")
        self.infer_btn = ttk.Button(action_frame, text="从约定推断",
                                    command=lambda: self._run_generation(self._execute_generate_by_inference),
                                    state="disabled")
        self.fk_btn.grid(row=0, column=0, padx=5, ipady=5, sticky="ew")
        self.infer_btn.grid(row=0, column=1, padx=5, ipady=5, sticky="ew")

        log_frame_inner = ttk.LabelFrame(parent, text="日志")
        log_frame_inner.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        log_frame_inner.columnconfigure(0, weight=1)
        log_frame_inner.rowconfigure(1, weight=1)

        self.progress_bar = ttk.Progressbar(log_frame_inner, mode='indeterminate')
        self.progress_bar.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        log_text_frame = ttk.Frame(log_frame_inner);
        log_text_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        log_text_frame.columnconfigure(0, weight=1);
        log_text_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_text_frame, height=5, state="disabled", wrap="word", relief="solid", borderwidth=1)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient="vertical", command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky="ns");
        self.log_text.config(yscrollcommand=log_scrollbar.set)

        self.log_text.tag_config("SUCCESS", foreground="green");
        self.log_text.tag_config("ERROR", foreground="red");
        self.log_text.tag_config("INFO", foreground="blue")

        log_btn_frame = ttk.Frame(log_frame_inner);
        log_btn_frame.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="ns")
        self.clear_log_btn = ttk.Button(log_btn_frame, text="清空", command=self._clear_log)
        self.open_file_btn = ttk.Button(log_btn_frame, text="打开", state="disabled", command=self._open_last_file)
        self.clear_log_btn.pack(pady=5, fill="x");
        self.open_file_btn.pack(pady=5, fill="x")

    def _create_settings_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        config_frame = ttk.LabelFrame(parent, text="配置文件管理")
        config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        config_frame.columnconfigure(0, weight=1)
        config_path_entry = ttk.Entry(config_frame, textvariable=self.config_file_path, state="readonly")
        config_path_entry.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        config_btn_frame = ttk.Frame(config_frame);
        config_btn_frame.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(config_btn_frame, text="加载", command=self._select_and_load_config).pack(side="left", padx=5)
        ttk.Button(config_btn_frame, text="另存为", command=self._save_config_as).pack(side="left", padx=5)

        style_frame = ttk.LabelFrame(parent, text="图表样式配置")
        style_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        style_frame.columnconfigure(1, weight=1)

        ttk.Label(style_frame, text="布局方向:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.layout_combo = ttk.Combobox(style_frame, state="readonly", values=list(self.layout_map.keys()), width=15);
        self.layout_combo.grid(row=0, column=1, padx=10, pady=8, sticky="w");
        self.layout_combo.bind("<<ComboboxSelected>>", self._on_style_changed)
        ttk.Label(style_frame, text="连线样式:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.spline_combo = ttk.Combobox(style_frame, state="readonly", values=list(self.spline_map.keys()), width=15);
        self.spline_combo.grid(row=1, column=1, padx=10, pady=8, sticky="w");
        self.spline_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        colors_map = [("背景色", 'bg_color'), ("默认节点色", 'node_color_default'), ("起始节点色", 'node_color_start'),
                      ("中间节点色", 'node_color_link'), ("末端节点色", 'node_color_end')]
        for i, (text, key) in enumerate(colors_map, 2):
            ttk.Label(style_frame, text=f"{text}:").grid(row=i, column=0, padx=10, pady=5, sticky="w")
            color_preview = tk.Label(style_frame, textvariable=self.graph_style[key], relief="sunken", width=10)
            color_preview.grid(row=i, column=1, padx=10, pady=5, sticky="w")
            color_btn = ttk.Button(style_frame, text="选择", command=lambda k=key: self._choose_color(k), width=6)
            color_btn.grid(row=i, column=2, padx=10, pady=5)
            self.graph_style[key].trace_add("write", lambda name, index, mode, var=self.graph_style[key],
                                                            preview=color_preview: preview.config(bg=var.get()))

        theme_frame = ttk.LabelFrame(parent, text="应用主题")
        theme_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        theme_switch = ttk.Checkbutton(theme_frame, text="切换为暗黑模式", style="Switch.TCheckbutton",
                                       command=lambda: sv_ttk.set_theme(
                                           "dark" if theme_switch.instate(['selected']) else "light"))
        theme_switch.pack(padx=10, pady=10, anchor="w")

    # --- 3. 核心逻辑 (Bug修复与健壮性增强) ---
    def _on_db_type_changed(self, event=None):
        is_sqlite = self.db_type.get() == "SQLite"
        for key in ["主机", "端口", "用户名", "密码"]: getattr(self, f"entry_{key}").config(
            state="disabled" if is_sqlite else "normal")

        self.db_search_var.set("")
        self.db_search_entry.config(state="disabled")
        self.db_listbox.delete(0, tk.END)
        self.db_listbox.config(state="disabled")

        self.fetch_tables_btn.config(state="disabled")
        self.table_search_var.set("")
        self.table_search_entry.config(state="disabled")
        self.table_listbox.delete(0, tk.END)
        self.table_listbox.config(state="disabled")

        self.fk_btn.config(state="disabled");
        self.infer_btn.config(state="disabled")

        if is_sqlite:
            self.connect_btn.config(text="📁 选择文件并加载表", command=self._browse_and_load_sqlite)
        else:
            self.connect_btn.config(text="🔗 连接并加载数据库", command=self._fetch_database_list)

    def _browse_and_load_sqlite(self):
        path = filedialog.askopenfilename(title="选择SQLite数据库文件",
                                          filetypes=[("SQLite DB", "*.db;*.sqlite;*.sqlite3"), ("All files", "*.*")])
        if not path: return
        self.db_entries['数据库'].delete(0, tk.END)
        self.db_entries['数据库'].insert(0, path)
        self.db_listbox.config(state="normal")
        self.db_listbox.delete(0, tk.END)
        self.db_listbox.insert(tk.END, os.path.basename(path))
        self.db_listbox.select_set(0)
        self._on_database_selected()

    def _get_selected_db(self):
        if self.db_type.get() == "SQLite":
            return self.db_entries['数据库'].get()
        selected_indices = self.db_listbox.curselection()
        if not selected_indices: return None
        return self.db_listbox.get(selected_indices[0])

    def _fetch_database_list(self):
        self._run_threaded(self._execute_fetch_databases)

    def _on_fetch_tables_button_click(self):
        db_name = self._get_selected_db()
        if not db_name:
            messagebox.showwarning("提示", "请先从数据库列表中选择一个数据库。")
            return
        self._run_threaded(self._execute_fetch_tables, args=(db_name,))

    def _run_generation(self, gen_method):
        selected_db = self._get_selected_db()
        selected_tables = self._get_selected_tables()
        if not selected_db or not selected_tables:
            self.after(0, lambda: messagebox.showwarning("操作中止", "请先选择一个数据库和至少一个表。"))
            return
        self._run_threaded(lambda: gen_method(selected_db, selected_tables))

    # --- BUG修复点 (核心) ---
    def _on_database_selected(self, event=None):
        # 1. 先重置下游UI的状态
        self.table_search_var.set("")
        self.table_search_entry.config(state="disabled")
        self.table_listbox.delete(0, tk.END)
        self.table_listbox.config(state="disabled")
        self.fk_btn.config(state="disabled")
        self.infer_btn.config(state="disabled")

        # 2. 激活“获取/刷新”按钮，并**立即调用其功能**
        self.fetch_tables_btn.config(state="normal")

        # 3. 移除之前的if判断，无论是什么数据库类型，选中后都自动加载表列表
        self._on_fetch_tables_button_click()

    def _get_selected_tables(self):
        return [self.table_listbox.get(i) for i in self.table_listbox.curselection()]

    def _select_all_tables(self):
        self.table_listbox.select_set(0, tk.END)

    def _deselect_all_tables(self):
        self.table_listbox.select_clear(0, tk.END)

    def _run_threaded(self, target_func, args=()):
        self._toggle_controls("disabled")
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()

    def _execute_fetch_databases(self):
        self._log("正在连接到服务器...", "INFO")
        try:
            engine = self._create_db_engine(use_db_name=False)
            with engine.connect() as connection:
                self._log(f"✅ 服务器连接成功 ({engine.dialect.name})！", "SUCCESS")
                inspector = inspect(engine)
                if engine.dialect.name == 'mysql':
                    result = connection.execute(text("SHOW DATABASES"))
                    db_names = [r[0] for r in result]
                    ignored = ['information_schema', 'mysql', 'performance_schema', 'sys']
                    db_names = [d for d in db_names if d not in ignored]
                else:
                    db_names = inspector.get_schema_names()
                    ignored = ['information_schema', 'pg_catalog', 'pg_toast']
                    db_names = [s for s in db_names if s not in ignored]
                self.after(0, self._populate_db_listbox, db_names)
        except Exception as e:
            self._handle_error(e, "连接失败")
        finally:
            self._toggle_controls("normal")

    def _populate_db_listbox(self, db_names):
        self.full_db_list = sorted(db_names)
        self.db_search_var.set("")  # 这会触发_filter_db_list来填充列表
        self.db_listbox.config(state="normal")
        self.db_search_entry.config(state="normal")

        if db_names:
            self._log(f"✅ 成功获取 {len(db_names)} 个数据库。", "SUCCESS")
        else:
            self._log("⚠️ 未找到任何用户数据库。", "ERROR")

    def _filter_db_list(self, *args):
        search_term = self.db_search_var.get().lower()
        self.db_listbox.delete(0, tk.END)
        for name in self.full_db_list:
            if search_term in name.lower():
                self.db_listbox.insert(tk.END, name)

    def _execute_fetch_tables(self, db_name):
        self._log(f"正在从数据库 '{db_name}' 获取表列表...", "INFO")
        try:
            engine = self._create_db_engine(db_name_override=db_name)
            inspector = inspect(engine)
            table_names = inspector.get_table_names()
            self.after(0, self._populate_table_listbox, table_names)
        except Exception as e:
            self._handle_error(e, "获取表失败")
        finally:
            self._toggle_controls("normal")

    def _populate_table_listbox(self, table_names):
        self.full_table_list = sorted(table_names)
        self.table_search_var.set("")  # 这会触发_filter_table_list来填充列表

        if table_names:
            self._log(f"✅ 成功获取 {len(table_names)} 个表。", "SUCCESS")
            self._select_all_tables()
            self.table_listbox.config(state="normal")
            self.table_search_entry.config(state="normal")
            self.fk_btn.config(state="normal");
            self.infer_btn.config(state="normal")
        else:
            self._log("⚠️ 未在该数据库中找到任何表。", "ERROR")
            self.table_listbox.config(state="disabled")
            self.table_search_entry.config(state="disabled")
            self.fk_btn.config(state="disabled");
            self.infer_btn.config(state="disabled")

    def _filter_table_list(self, *args):
        search_term = self.table_search_var.get().lower()
        selected_before_filter = self._get_selected_tables()
        self.table_listbox.delete(0, tk.END)
        filtered_list = [name for name in self.full_table_list if search_term in name.lower()]
        for name in filtered_list:
            self.table_listbox.insert(tk.END, name)
            if name in selected_before_filter:
                last_index = self.table_listbox.size() - 1
                self.table_listbox.select_set(last_index)

    def _execute_generate_by_fk(self, db_name, selected_tables):
        try:
            self._log("--- 开始基于外键生成 ---", "INFO")
            engine, inspector = self._create_db_engine(db_name_override=db_name), inspect(
                self._create_db_engine(db_name_override=db_name))
            relations = []
            self._log(f"正在分析 {len(selected_tables)} 个选定表的外键...", "INFO")
            for table_name in selected_tables:
                for fk in inspector.get_foreign_keys(table_name):
                    if fk['referred_table'] in selected_tables and fk['constrained_columns'] and fk['referred_columns']:
                        relations.append(
                            (table_name, fk['constrained_columns'][0], fk['referred_table'], fk['referred_columns'][0]))
            self._render_graph(relations, 'fk', f"{db_name} (FK Based)")
        except Exception as e:
            self._handle_error(e, "生成失败")
        finally:
            self._toggle_controls("normal")

    def _execute_generate_by_inference(self, db_name, selected_tables):
        try:
            self._log("--- 开始基于约定推断 ---", "INFO")
            engine = self._create_db_engine(db_name_override=db_name)
            inspector, tables_metadata, relations = inspect(engine), {}, []
            self._log("正在获取所有表的元数据以供推断...", "INFO")
            all_tables_in_db = inspector.get_table_names()
            for tbl_name in all_tables_in_db:
                tables_metadata[tbl_name] = {'cols': [c['name'] for c in inspector.get_columns(tbl_name)],
                                             'pks': inspector.get_pk_constraint(tbl_name)['constrained_columns']}

            self._log("正在根据命名约定推断关系...", "INFO")
            for t_name in selected_tables:
                info = tables_metadata.get(t_name, {})
                for c_name in info.get('cols', []):
                    if c_name.endswith('_id') and c_name not in info.get('pks', []):
                        prefix = c_name[:-3]
                        possible_targets = [prefix, f"{prefix}s"]
                        for target_table in possible_targets:
                            if target_table in selected_tables and target_table in tables_metadata:
                                target_pks = tables_metadata[target_table].get('pks', [])
                                if len(target_pks) == 1:
                                    relations.append((t_name, c_name, target_table, target_pks[0]));
                                    break
            self._render_graph(relations, 'inferred', f"{db_name} (Inferred)")
        except Exception as e:
            self._handle_error(e, "推断失败")
        finally:
            self._toggle_controls("normal")

    def _create_db_engine(self, use_db_name=True, db_name_override=None):
        db_type, details = self.db_type.get(), {k: v.get() for k, v in self.db_entries.items()}
        dialect = self.db_dialect_map.get(db_type)
        if not dialect: raise ValueError(f"不支持的数据库类型: {db_type}")
        if db_type == "SQLite":
            path = self._get_selected_db()
            if not path: raise ValueError("SQLite需要指定数据库文件路径。")
            return create_engine(f"sqlite:///{path}")
        else:
            db_name = db_name_override if use_db_name else ""
            return create_engine(
                f"{dialect}://{details['用户名']}:{details['密码']}@{details['主机']}:{details['端口']}/{db_name or ''}")

    def _toggle_controls(self, state="normal"):
        self.after(0, self.__update_controls_state, state)

    def __update_controls_state(self, state):
        final_state = "normal" if state == "normal" else "disabled"
        is_sqlite = self.db_type.get() == "SQLite"

        if final_state == "disabled":
            self.progress_bar.start(10)
            self.connect_btn.config(state='disabled')
            self.fetch_tables_btn.config(state='disabled')
            self.fk_btn.config(state='disabled')
            self.infer_btn.config(state='disabled')
        else:
            self.progress_bar.stop()
            self.connect_btn.config(state='normal')

            if self._get_selected_db():
                self.fetch_tables_btn.config(state='normal')
            else:
                self.fetch_tables_btn.config(state='disabled')

            if self.table_listbox.size() > 0:
                self.fk_btn.config(state='normal')
                self.infer_btn.config(state='normal')
            else:
                self.fk_btn.config(state='disabled')
                self.infer_btn.config(state='disabled')

    def _handle_error(self, e, title):
        self._log(f"❌ {title}失败: {e}", "ERROR")
        self.after(0, lambda: messagebox.showerror(title, f"{title}时发生错误:\n\n{e}"))

    def _render_graph(self, relations, suffix, label):
        db_name = self._get_selected_db()
        if not db_name: return
        if not relations: self._log("⚠️ 未找到任何关系，任务中止。", "ERROR"); self.after(0,
                                                                                        lambda: messagebox.showwarning(
                                                                                            "提示",
                                                                                            "在选定的表之间未能找到任何关系。")); return
        self._log(f"✅ 找到 {len(relations)} 条关系，开始渲染图表...", "INFO")
        s = self.graph_style
        graph_attrs = {'rankdir': s['layout'].get(), 'bgcolor': s['bg_color'].get(), 'pad': '1.0',
                       'splines': s['spline'].get(), 'nodesep': '0.8', 'ranksep': '1.2', 'label': f"\n{label}",
                       'fontsize': '22', 'fontname': 'Segoe UI,Verdana,Arial', 'fontcolor': '#333333',
                       'overlap': 'false'}
        node_attrs = {'style': 'filled,rounded', 'shape': 'box', 'fontname': 'Segoe UI,Verdana,Arial', 'fontsize': '14',
                      'fontcolor': '#2D2D2D', 'margin': '0.4', 'color': '#666666'}
        edge_attrs = {'color': '#757575', 'arrowsize': '0.9', 'penwidth': '1.5', 'fontsize': '11',
                      'fontname': 'Verdana,Arial', 'fontcolor': '#00008B'}
        dot = Digraph(format="png", graph_attr=graph_attrs, node_attr=node_attrs, edge_attr=edge_attrs)
        all_nodes = set()
        for from_table, _, to_table, _ in relations: all_nodes.add(from_table); all_nodes.add(to_table)
        in_d, out_d = {n: 0 for n in all_nodes}, {n: 0 for n in all_nodes}
        for f, _, t, _ in relations: out_d[f] += 1; in_d[t] += 1
        for node in all_nodes:
            color = s['node_color_default'].get()
            if out_d[node] > 0 and in_d[node] == 0:
                color = s['node_color_start'].get()
            elif out_d[node] > 0 and in_d[node] > 0:
                color = s['node_color_link'].get()
            elif out_d[node] == 0 and in_d[node] > 0:
                color = s['node_color_end'].get()
            dot.node(node, fillcolor=color)
        for from_table, from_col, to_table, to_col in relations:
            edge_label = f" {from_table}.{from_col} = {to_table}.{to_col} "
            dot.edge(from_table, to_table, label=edge_label, tooltip=edge_label)
        output_filename = os.path.join(self.output_path.get(),
                                       f"relation_{os.path.basename(db_name).replace(':', '_')}_{suffix}")
        try:
            generated_path = dot.render(output_filename, cleanup=True, view=False)
            self.last_generated_file = generated_path
            self._log(f"🎉 图表已生成: {generated_path}", "SUCCESS")
            self.after(0, lambda: self.open_file_btn.config(state="normal"))
            self.after(0, lambda: messagebox.showinfo("完成", f"图表已成功生成！\n路径: {generated_path}"))
        except Exception as e:
            self._handle_error(e, "渲染错误")

    def _on_style_changed(self, event):
        widget = event.widget
        if widget == self.layout_combo:
            self.graph_style['layout'].set(self.layout_map.get(self.layout_combo.get()))
        elif widget == self.spline_combo:
            self.graph_style['spline'].set(self.spline_map.get(self.spline_combo.get()))

    def _update_ui_from_style_vars(self):
        self.layout_combo.set(self.layout_map_rev.get(self.graph_style['layout'].get()));
        self.spline_combo.set(self.spline_map_rev.get(self.graph_style['spline'].get()))

    def _log(self, msg, level="INFO"):
        self.after(0, self.__update_log, msg, level)

    def __update_log(self, msg, level):
        self.log_text.config(state="normal");
        self.log_text.insert(tk.END, f"[{level}] {msg}\n", level);
        self.log_text.see(tk.END);
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal");
        self.log_text.delete(1.0, tk.END);
        self.log_text.config(state="disabled")

    def _open_last_file(self):
        if self.last_generated_file and os.path.exists(self.last_generated_file):
            webbrowser.open(self.last_generated_file)
        else:
            messagebox.showwarning("警告", "找不到上次生成的文件。")

    def _browse_directory(self):
        path = filedialog.askdirectory(initialdir=self.output_path.get())
        if path: self.output_path.set(path); self._log(f"输出路径已更新: {path}", "INFO")

    def _choose_color(self, key):
        initial_color = self.graph_style[key].get()
        color_code = colorchooser.askcolor(title="选择颜色", initialcolor=initial_color)
        if color_code and color_code[1]:
            self.graph_style[key].set(color_code[1])


if __name__ == "__main__":
    app = UltimateBeautifiedApp()
    app.mainloop()