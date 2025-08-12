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

# 【修正】引入SQLAlchemy。ImportError是Python内置异常，无需从sqlalchemy.exc导入。
from sqlalchemy import create_engine, inspect
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
        self.title("数据库关系图生成器")
        self.geometry("700x900")

        # --- 数据模型 ---
        self.db_entries = {}
        self.output_path = tk.StringVar()
        self.last_generated_file = None
        self.config_file_path = tk.StringVar()
        self.db_type = tk.StringVar()

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

        # 判断程序是否被打包 (frozen)
        if getattr(sys, 'frozen', False):
            # 如果是打包后的EXE文件，则获取EXE文件所在的目录
            application_path = os.path.dirname(sys.executable)
        else:
            # 如果是直接运行的.py脚本，则获取脚本所在的目录
            application_path = os.path.dirname(os.path.abspath(__file__))

        # 将默认配置文件路径设置在程序所在目录下
        default_config_path = os.path.join(application_path, "relationship_diagram_config.json")
        self.config_file_path.set(default_config_path)
        self._load_config()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # --- 1. 配置持久化 ---
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
                if key != "密码": entry.delete(0, tk.END); entry.insert(0, db_conf.get(key, ''))
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
                  "graph_style": {key: var.get() for key, var in self.graph_style.items()}, }
        try:
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self.config_file_path.set(target_path)
            self._log("✅ 配置已保存。", "SUCCESS")
        except Exception as e:
            self._log(f"保存配置失败: {e}", "ERROR"); self.after(0, lambda: messagebox.showerror("保存失败",
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
        self._save_config(); self.destroy()

    def _get_default_styles(self):
        return {'layout': 'TB', 'spline': 'ortho', 'bg_color': '#FAFAFA', 'node_color_default': '#87CEEB',
                'node_color_start': '#FFDDC1', 'node_color_link': '#D1FFBD', 'node_color_end': '#E0BBE4'}

    # --- 2. UI创建 ---
    def _create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        main_tab, settings_tab = ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(main_tab, text=' 🚀 生成器 ');
        notebook.add(settings_tab, text=' 🎨 样式与配置 ')
        self._create_main_tab(main_tab);
        self._create_settings_tab(settings_tab)

    def _create_main_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        conn_frame = ttk.LabelFrame(parent, text=" 🗄️ 数据库连接信息 ")
        conn_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew");
        conn_frame.columnconfigure(1, weight=1)
        ttk.Label(conn_frame, text="数据库类型:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.db_type_combo = ttk.Combobox(conn_frame, textvariable=self.db_type, state="readonly",
                                          values=list(self.db_dialect_map.keys()))
        self.db_type_combo.grid(row=0, column=1, padx=10, pady=8, sticky="w")
        self.db_type_combo.bind("<<ComboboxSelected>>", self._on_db_type_changed)
        labels = ["主机:", "端口:", "用户名:", "密码:", "数据库:"]
        for i, label_text in enumerate(labels, 1):
            key = label_text.strip(':')
            label = ttk.Label(conn_frame, text=label_text)
            label.grid(row=i, column=0, padx=10, pady=8, sticky="w")
            entry = ttk.Entry(conn_frame, show="*" if "密码" in label_text else "")
            entry.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
            self.db_entries[key] = entry
            setattr(self, f"label_{key}", label);
            setattr(self, f"entry_{key}", entry)
        self.db_browse_btn = ttk.Button(conn_frame, text="浏览...", command=self._browse_db_file)
        self.db_browse_btn.grid(row=5, column=2, padx=5)
        out_frame = ttk.LabelFrame(parent, text=" 📁 输出路径 ")
        out_frame.grid(row=1, column=0, padx=5, pady=10, sticky="ew");
        out_frame.columnconfigure(0, weight=1)
        path_entry = ttk.Entry(out_frame, textvariable=self.output_path, state="readonly")
        path_entry.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        browse_btn = ttk.Button(out_frame, text="浏览...", command=self._browse_directory)
        browse_btn.grid(row=0, column=1, padx=10, pady=8)
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=2, column=0, pady=10, sticky="ew");
        action_frame.columnconfigure((0, 1, 2), weight=1)
        self.test_btn = ttk.Button(action_frame, text="✔️ 测试连接", command=self._test_connection,
                                   style="Accent.TButton")
        self.fk_btn = ttk.Button(action_frame, text="🔗 基于外键生成",
                                 command=lambda: self._run_generation(self._execute_generate_by_fk))
        self.infer_btn = ttk.Button(action_frame, text="💡 基于约定推断",
                                    command=lambda: self._run_generation(self._execute_generate_by_inference))
        self.test_btn.grid(row=0, column=0, padx=5, ipady=5, sticky="ew");
        self.fk_btn.grid(row=0, column=1, padx=5, ipady=5, sticky="ew");
        self.infer_btn.grid(row=0, column=2, padx=5, ipady=5, sticky="ew")
        log_frame = ttk.LabelFrame(parent, text=" 📈 状态日志 ")
        log_frame.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")
        parent.rowconfigure(3, weight=1);
        log_frame.columnconfigure(0, weight=1);
        log_frame.rowconfigure(1, weight=1)
        self.progress_bar = ttk.Progressbar(log_frame, mode='indeterminate')
        self.progress_bar.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word", relief="flat", borderwidth=0)
        self.log_text.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.log_text.tag_config("SUCCESS", foreground="green");
        self.log_text.tag_config("ERROR", foreground="red");
        self.log_text.tag_config("INFO", foreground="blue")
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=1, padx=5, pady=5, sticky="ns")
        self.clear_log_btn = ttk.Button(log_btn_frame, text="清空", command=self._clear_log)
        self.open_file_btn = ttk.Button(log_btn_frame, text="打开图片", state="disabled", command=self._open_last_file)
        self.clear_log_btn.pack(pady=5, fill="x");
        self.open_file_btn.pack(pady=5, fill="x")

    def _create_settings_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        config_frame = ttk.LabelFrame(parent, text=" ⚙️ 配置文件管理")
        config_frame.grid(row=0, column=0, padx=5, pady=10, sticky="ew");
        config_frame.columnconfigure(0, weight=1)
        config_path_entry = ttk.Entry(config_frame, textvariable=self.config_file_path, state="readonly")
        config_path_entry.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        config_path_entry.tooltip = ToolTip(config_path_entry, "当前使用的配置文件路径。关闭程序时会自动保存到此路径。")
        config_btn_frame = ttk.Frame(config_frame)
        config_btn_frame.grid(row=0, column=1, padx=5, pady=5)
        load_btn = ttk.Button(config_btn_frame, text="加载...", command=self._select_and_load_config)
        load_btn.pack(side="left", padx=5)
        save_as_btn = ttk.Button(config_btn_frame, text="另存为...", command=self._save_config_as)
        save_as_btn.pack(side="left", padx=5)
        theme_frame = ttk.LabelFrame(parent, text=" 🎨 应用主题 ")
        theme_frame.grid(row=1, column=0, padx=5, pady=10, sticky="ew")
        theme_switch = ttk.Checkbutton(theme_frame, text="切换为暗黑模式", style="Switch.TCheckbutton",
                                       command=lambda: sv_ttk.set_theme(
                                           "dark" if theme_switch.instate(['selected']) else "light"))
        theme_switch.pack(padx=10, pady=10)
        style_frame = ttk.LabelFrame(parent, text=" 🖌️ 图表样式配置 ")
        style_frame.grid(row=2, column=0, padx=5, pady=5, sticky="ew");
        style_frame.columnconfigure(1, weight=1)
        ttk.Label(style_frame, text="布局方向:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.layout_combo = ttk.Combobox(style_frame, state="readonly", values=list(self.layout_map.keys()), width=15)
        self.layout_combo.grid(row=0, column=1, padx=10, pady=8, sticky="w")
        self.layout_combo.bind("<<ComboboxSelected>>", self._on_style_changed)
        ttk.Label(style_frame, text="连线样式:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.spline_combo = ttk.Combobox(style_frame, state="readonly", values=list(self.spline_map.keys()), width=15)
        self.spline_combo.grid(row=1, column=1, padx=10, pady=8, sticky="w")
        self.spline_combo.bind("<<ComboboxSelected>>", self._on_style_changed)
        colors_map = [("背景色", 'bg_color'), ("默认节点色", 'node_color_default'), ("起始节点色", 'node_color_start'),
                      ("中间节点色", 'node_color_link'), ("末端节点色", 'node_color_end')]
        for i, (text, key) in enumerate(colors_map, 2):
            ttk.Label(style_frame, text=f"{text}:").grid(row=i, column=0, padx=10, pady=5, sticky="w")
            color_btn = ttk.Button(style_frame, text="选择颜色", command=lambda k=key: self._choose_color(k))
            color_btn.grid(row=i, column=2, padx=10, pady=5)
            color_preview = tk.Label(style_frame, textvariable=self.graph_style[key], relief="sunken", width=10)
            color_preview.grid(row=i, column=1, padx=10, pady=5, sticky="w")
            self.graph_style[key].trace_add("write", lambda name, index, mode, var=self.graph_style[key],
                                                            preview=color_preview: preview.config(bg=var.get()))

    # --- 3. 核心逻辑 ---
    def _on_db_type_changed(self, event=None):
        selected_db, is_sqlite = self.db_type.get(), self.db_type.get() == "SQLite"
        for key in ["主机", "端口", "用户名", "密码"]:
            state = "disabled" if is_sqlite else "normal"
            getattr(self, f"label_{key}").config(state=state)
            entry = getattr(self, f"entry_{key}")
            entry.config(state=state)
            if event: entry.delete(0, tk.END)
        self.label_数据库.config(text="数据库文件:" if is_sqlite else "数据库:")
        if event: self.entry_数据库.delete(0, tk.END)
        if is_sqlite:
            self.db_browse_btn.grid()
        else:
            self.db_browse_btn.grid_remove()

    def _browse_db_file(self):
        path = filedialog.askopenfilename(title="选择SQLite数据库文件",
                                          filetypes=[("SQLite Database", "*.db"), ("SQLite3", "*.sqlite3"),
                                                     ("All files", "*.*")])
        if path: self.db_entries["数据库"].delete(0, tk.END); self.db_entries["数据库"].insert(0, path)

    def _on_style_changed(self, event):
        widget = event.widget
        if widget == self.layout_combo:
            self.graph_style['layout'].set(self.layout_map.get(self.layout_combo.get()))
        elif widget == self.spline_combo:
            self.graph_style['spline'].set(self.spline_map.get(self.spline_combo.get()))

    def _update_ui_from_style_vars(self):
        self.layout_combo.set(self.layout_map_rev.get(self.graph_style['layout'].get()));
        self.spline_combo.set(self.spline_map_rev.get(self.graph_style['spline'].get()))

    def _choose_color(self, key):
        color_code = colorchooser.askcolor(title="选择颜色", initialcolor=self.graph_style[key].get());
        if color_code[1]: self.graph_style[key].set(color_code[1])

    def _log(self, msg, level="INFO"):
        self.after(0, self.__update_log, msg, level)

    def __update_log(self, msg, level):
        self.log_text.config(state="normal"); self.log_text.insert(tk.END, f"[{level}] {msg}\n",
                                                                   level); self.log_text.see(
            tk.END); self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal"); self.log_text.delete(1.0, tk.END); self.log_text.config(state="disabled")

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
        self._toggle_controls("disabled"); thread = threading.Thread(target=target_func, daemon=True); thread.start()

    # --- 数据库核心逻辑 ---
    def _create_db_engine(self):
        db_type_key, details = self.db_type.get(), {k: v.get() for k, v in self.db_entries.items()}
        dialect = self.db_dialect_map.get(db_type_key)
        if not dialect: raise ValueError(f"不支持的数据库类型: {db_type_key}")
        if db_type_key == "SQLite":
            if not details['数据库']: raise ValueError("SQLite需要指定数据库文件路径。")
            return create_engine(f"{dialect}:///{details['数据库']}")
        else:
            return create_engine(
                f"{dialect}://{details['用户名']}:{details['密码']}@{details['主机']}:{details['端口']}/{details['数据库']}")

    def _test_connection(self):
        self._run_threaded(self._execute_test_connection)

    def _run_generation(self, generation_method):
        self._run_threaded(generation_method)

    def _execute_test_connection(self):
        try:
            self._log("正在创建数据库引擎...", "INFO")
            engine = self._create_db_engine()
            self._log(f"正在连接 ({engine.dialect.name})...", "INFO")
            with engine.connect() as connection:
                self._log("✅ 连接成功！", "SUCCESS"); self.after(0, lambda: messagebox.showinfo("成功",
                                                                                               f"数据库连接成功！\n方言: {engine.dialect.name}"))
        except ImportError as e:
            self._handle_error(e, "驱动错误",
                               f"数据库驱动未安装。\n请根据选择的数据库类型安装对应库，例如 'pip install {e.name}'。\n\n错误详情: {e}")
        except SQLAlchemyError as e:
            self._handle_error(e, "连接失败")
        except Exception as e:
            self._handle_error(e, "未知错误")
        finally:
            self._toggle_controls("normal")

    def _execute_generate_by_fk(self):
        try:
            self._log("--- 开始基于外键生成 (SQLAlchemy) ---", "INFO")
            engine, inspector, relations = self._create_db_engine(), inspect(self._create_db_engine()), set()
            schemas_to_scan = [None]
            if engine.dialect.name == 'postgresql':
                ignored = ['information_schema', 'pg_catalog', 'pg_toast']
                schemas_to_scan = [s for s in inspector.get_schema_names() if s not in ignored]
                self._log(f"检测到PostgreSQL，将扫描Schemas: {schemas_to_scan}", "INFO")
            for schema in schemas_to_scan:
                for table_name in inspector.get_table_names(schema=schema):
                    for fk in inspector.get_foreign_keys(table_name, schema=schema): relations.add(
                        (table_name, fk['referred_table']))
            self._render_graph(relations, 'fk', f"{self.db_entries['数据库'].get()} Schema (FK Based)")
        except ImportError as e:
            self._handle_error(e, "驱动错误",
                               f"数据库驱动未安装。\n请根据选择的数据库类型安装对应库，例如 'pip install {e.name}'。\n\n错误详情: {e}")
        except SQLAlchemyError as e:
            self._handle_error(e, "生成失败")
        except Exception as e:
            self._handle_error(e, "未知错误")
        finally:
            self._toggle_controls("normal")

    def _execute_generate_by_inference(self):
        try:
            self._log("--- 开始基于约定推断 (SQLAlchemy) ---", "INFO")
            inspector, tables_metadata, relations = inspect(self._create_db_engine()), {}, set()
            for tbl_name in inspector.get_table_names(): tables_metadata[tbl_name] = {
                'cols': [c['name'] for c in inspector.get_columns(tbl_name)],
                'pks': inspector.get_pk_constraint(tbl_name)['constrained_columns']}
            self._log("正在根据命名约定推断关系...", "INFO")
            for t_name, info in tables_metadata.items():
                for c_name in info['cols']:
                    if c_name.endswith('_id') and c_name not in info['pks']:
                        prefix = c_name[:-3]
                        for target_table in tables_metadata:
                            if target_table == prefix or target_table == f"{prefix}s":
                                if 'id' in tables_metadata.get(target_table, {}).get('pks', []): relations.add(
                                    (t_name, target_table)); break
            self._render_graph(relations, 'inferred', f"{self.db_entries['数据库'].get()} Schema (Inferred)")
        except ImportError as e:
            self._handle_error(e, "驱动错误",
                               f"数据库驱动未安装。\n请根据选择的数据库类型安装对应库，例如 'pip install {e.name}'。\n\n错误详情: {e}")
        except SQLAlchemyError as e:
            self._handle_error(e, "推断失败")
        except Exception as e:
            self._handle_error(e, "未知错误")
        finally:
            self._toggle_controls("normal")

    def _handle_error(self, e, title, custom_msg=None):
        self._log(f"❌ {title}失败: {e}", "ERROR")
        msg = custom_msg or f"{title}失败:\n{e}"
        self.after(0, lambda: messagebox.showerror(title, msg))

    # --- 渲染引擎 ---
    def _render_graph(self, relations, suffix, label):
        if not relations: self._log("⚠️ 未找到任何关系，任务中止。", "ERROR"); self.after(0,
                                                                                        lambda: messagebox.showwarning(
                                                                                            "提示",
                                                                                            "未能找到任何表间关系。")); return
        self._log(f"✅ 找到 {len(relations)} 条关系，开始渲染图表...", "INFO")
        s = self.graph_style
        graph_attrs = {'rankdir': s['layout'].get(), 'bgcolor': s['bg_color'].get(), 'pad': '1.0',
                       'splines': s['spline'].get(), 'nodesep': '0.8', 'ranksep': '1.2', 'label': f"\n{label}",
                       'fontsize': '22', 'fontname': 'Segoe UI,Verdana,Arial', 'fontcolor': '#333333',
                       'overlap': 'false'}
        node_attrs = {'style': 'filled,rounded', 'shape': 'box', 'fontname': 'Segoe UI,Verdana,Arial', 'fontsize': '14',
                      'fontcolor': '#2D2D2D', 'margin': '0.4', 'color': '#666666'}
        edge_attrs = {'color': '#757575', 'arrowsize': '0.9', 'penwidth': '1.5'}
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
        if self.db_type.get() == 'SQLite' and db_name: db_name = os.path.splitext(os.path.basename(db_name))[0]
        output_filename = os.path.join(self.output_path.get(), f"relation_{db_name}_{suffix}")
        try:
            generated_path = dot.render(output_filename, cleanup=True, view=False)
            self.last_generated_file = generated_path
            self._log(f"🎉 图表已生成: {generated_path}", "SUCCESS")
            self.after(0, lambda: self.open_file_btn.config(state="normal"))
            self.after(0, lambda: messagebox.showinfo("完成", f"图表已成功生成！\n路径: {generated_path}"))
        except Exception as e:
            self._handle_error(e, "渲染错误",
                               f"无法调用Graphviz生成图片，请确保它已安装并添加到系统PATH环境变量。\n\n错误: {e}")


if __name__ == "__main__":
    app = UltimateBeautifiedApp()
    app.mainloop()