import pymysql
from graphviz import Digraph
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import threading
import sv_ttk  # 导入新主题库


# 使用面向对象的方式构建整个应用
class RelationDiagramApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("数据库关系图生成器 Pro ✨")
        self.geometry("600x650")

        # --- 设置主题 ---
        sv_ttk.set_theme("dark")  # 可选 'light' 或 'dark'

        # --- 数据成员 ---
        self.output_path = tk.StringVar(value=os.getcwd())
        self.graph_layout = tk.StringVar(value='TB')  # TB: Top-to-Bottom, LR: Left-to-Right

        # --- 创建并布局UI组件 ---
        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        # 1. 数据库连接信息区域
        conn_frame = ttk.LabelFrame(main_frame, text=" 🗄️ 数据库连接信息 ")
        conn_frame.pack(fill="x", padx=5, pady=5)
        conn_frame.columnconfigure(1, weight=1)

        labels = ["主机:", "端口:", "用户名:", "密码:", "数据库:"]
        defaults = ["localhost", "3306", "root", "", "sky_take_out"]  # 预填示例数据库
        self.entries = {}
        for i, (label_text, default_val) in enumerate(zip(labels, defaults)):
            ttk.Label(conn_frame, text=label_text).grid(row=i, column=0, padx=10, pady=8, sticky="w")
            entry = ttk.Entry(conn_frame, show="*" if "密码" in label_text else "")
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
            self.entries[label_text.strip(':')] = entry

        # 2. 图表与输出设置
        settings_frame = ttk.LabelFrame(main_frame, text=" 🎨 图表与输出设置 ")
        settings_frame.pack(fill="x", padx=5, pady=10)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="布局方向:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        layout_menu = ttk.OptionMenu(settings_frame, self.graph_layout, 'TB', 'TB', 'LR')
        layout_menu.grid(row=0, column=1, padx=10, pady=8, sticky="w")

        ttk.Label(settings_frame, text="输出路径:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        path_entry = ttk.Entry(settings_frame, textvariable=self.output_path, state="readonly")
        path_entry.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        browse_button = ttk.Button(settings_frame, text="浏览...", command=self._browse_directory)
        browse_button.grid(row=1, column=2, padx=(0, 10), pady=8)

        # 3. 操作按钮区域
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x", pady=10)
        action_frame.columnconfigure((0, 1, 2), weight=1)

        self.test_conn_button = ttk.Button(action_frame, text="✔️ 测试连接", command=self._test_connection,
                                           style="Accent.TButton")
        self.test_conn_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.fk_button = ttk.Button(action_frame, text="🔗 基于外键生成",
                                    command=lambda: self._run_generation(self._generate_diagram_by_fk))
        self.fk_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.infer_button = ttk.Button(action_frame, text="💡 基于约定推断",
                                       command=lambda: self._run_generation(self._generate_diagram_by_inference))
        self.infer_button.grid(row=0, column=2, padx=5, sticky="ew")

        # 4. 进度条与日志
        progress_frame = ttk.LabelFrame(main_frame, text=" 📈 状态与日志 ")
        progress_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill="x", padx=10, pady=5, expand=True)

        self.log_text = tk.Text(progress_frame, height=10, state="disabled", wrap="word", relief="flat")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    # --- 后端逻辑方法 (基本不变，但增加了UI交互) ---

    def _log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.update_idletasks()

    def _toggle_controls(self, state="normal"):
        if state == "disabled":
            self.progress_bar.start(10)
        else:
            self.progress_bar.stop()

        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                for widget in child.winfo_children():
                    if isinstance(widget, (ttk.Button, ttk.OptionMenu, ttk.Entry)):
                        widget.config(state=state)

    def _browse_directory(self):
        path = filedialog.askdirectory(initialdir=self.output_path.get())
        if path:
            self.output_path.set(path)
            self._log(f"输出路径已设置为: {path}")

    def _get_connection_details(self):
        details = {k: v.get() for k, v in self.entries.items()}
        details['端口'] = int(details['端口'])
        return details

    def _test_connection(self):
        self._toggle_controls("disabled")
        self._log("正在尝试连接到数据库...")
        try:
            details = self._get_connection_details()
            conn = pymysql.connect(
                host=details['主机'], port=details['端口'], user=details['用户名'],
                password=details['密码'], database=details['数据库']
            )
            conn.close()
            self._log("✅ 连接成功！")
            messagebox.showinfo("成功", "数据库连接成功！")
        except Exception as e:
            self._log(f"❌ 连接失败: {e}")
            messagebox.showerror("错误", f"连接失败:\n{e}")
        finally:
            self.after(100, lambda: self._toggle_controls("normal"))

    def _run_generation(self, generation_function):
        self._toggle_controls("disabled")
        thread = threading.Thread(target=generation_function)
        thread.start()

    # --- 核心：美化图表渲染 ---

    def _render_beautiful_graph(self, relations, filename_suffix, graph_label):
        if not relations:
            self._log(f"未找到任何关系，无法生成图表。")
            self.after(100, lambda: messagebox.showwarning("提示", "未能找到任何表间关系。"))
            return

        db_name = self.entries['数据库'].get()

        # 1. 定义样式
        graph_attrs = {
            'rankdir': self.graph_layout.get(),  # 'TB' or 'LR'
            'bgcolor': '#F0F0F0',
            'pad': '0.5',
            'splines': 'ortho',  # 使用直角连线，更整洁
            'nodesep': '0.8',
            'ranksep': '1',
            'label': graph_label,
            'fontsize': '20',
            'fontname': 'Helvetica, Arial, sans-serif',
            'fontcolor': '#333333'
        }
        node_attrs = {
            'style': 'filled,rounded',
            'shape': 'box',
            'fontname': 'Helvetica, Arial, sans-serif',
            'fontsize': '12',
            'margin': '0.4'
        }
        edge_attrs = {
            'color': '#888888',
            'arrowsize': '0.8',
            'penwidth': '1.2'
        }

        dot = Digraph(comment=f'{db_name} Schema', format="png",
                      graph_attr=graph_attrs, node_attr=node_attrs, edge_attr=edge_attrs)

        # 2. 分析节点类型以进行颜色编码
        in_degrees = {node: 0 for node in set(sum(relations, ()))}
        out_degrees = {node: 0 for node in set(sum(relations, ()))}
        for from_node, to_node in relations:
            out_degrees[from_node] += 1
            in_degrees[to_node] += 1

        # 3. 添加节点和边
        all_nodes = set(in_degrees.keys())
        for node in all_nodes:
            color = '#87CEEB'  # 默认颜色 (天蓝色)
            if out_degrees[node] > 0 and in_degrees[node] == 0:
                color = '#FFDDC1'  # 起始节点/主要业务表 (淡橙色)
            elif out_degrees[node] >= 2 and in_degrees[node] >= 1:
                color = '#D1FFBD'  # 连接表 (淡绿色)
            elif out_degrees[node] == 0 and in_degrees[node] > 0:
                color = '#E0BBE4'  # 基础数据/被引用表 (淡紫色)

            dot.node(node, fillcolor=color)

        for table, ref_table in relations:
            dot.edge(table, ref_table)

        output_file_name = f"mysql_relation_{db_name}_{filename_suffix}"
        output_file = os.path.join(self.output_path.get(), output_file_name)
        self._log(f"正在渲染美化版图表到 {output_file}.png ...")
        dot.render(output_file, cleanup=True, view=False)
        self._log(f"✅ 图表生成成功: {output_file}.png")
        self.after(100, lambda: messagebox.showinfo("完成", f"图表已成功生成！\n路径: {output_file}.png"))

    # --- 生成逻辑函数（调用新的渲染器） ---

    def _generate_diagram_by_fk(self):
        try:
            self._log("--- 开始基于外键生成图表 ---")
            details = self._get_connection_details()
            # ... (数据库查询逻辑不变) ...
            conn = pymysql.connect(**{'host': details['主机'], 'port': details['端口'], 'user': details['用户名'],
                                      'password': details['密码'], 'database': details['数据库']},
                                   cursorclass=pymysql.cursors.DictCursor)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name, referenced_table_name FROM information_schema.KEY_COLUMN_USAGE WHERE table_schema = %s AND referenced_table_name IS NOT NULL",
                    (details['数据库'],))
                relations = {(row['table_name'], row['referenced_table_name']) for row in cur.fetchall()}
            conn.close()
            # 调用新的美化渲染函数
            self._render_beautiful_graph(relations, 'fk_beautiful', f"{details['数据库']} Schema (FK Based)")
        except Exception as e:
            self._log(f"❌ 生成失败: {e}")
            self.after(100, lambda: messagebox.showerror("错误", f"生成失败:\n{e}"))
        finally:
            self.after(100, lambda: self._toggle_controls("normal"))

    def _generate_diagram_by_inference(self):
        try:
            self._log("--- 开始基于约定推断图表 ---")
            details = self._get_connection_details()
            # ... (数据库查询和推断逻辑不变) ...
            conn = pymysql.connect(**{'host': details['主机'], 'port': details['端口'], 'user': details['用户名'],
                                      'password': details['密码'], 'database': details['数据库']},
                                   cursorclass=pymysql.cursors.DictCursor)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_KEY FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s",
                    (details['数据库'],))
                all_columns = cur.fetchall()
            conn.close()
            tables = {}
            for col in all_columns:
                tbl = col['TABLE_NAME']
                if tbl not in tables: tables[tbl] = {'columns': [], 'pk': None}
                tables[tbl]['columns'].append(col['COLUMN_NAME'])
                if col['COLUMN_KEY'] == 'PRI': tables[tbl]['pk'] = col['COLUMN_NAME']
            relations = set()
            table_names = list(tables.keys())
            for table_name, info in tables.items():
                for col_name in info['columns']:
                    if col_name.endswith('_id') and col_name != info.get('pk'):
                        prefix = col_name[:-3]
                        for target_table in table_names:
                            if target_table.rstrip('s') == prefix and tables[target_table].get('pk') == 'id':
                                relations.add((table_name, target_table))
                                break
            # 调用新的美化渲染函数
            self._render_beautiful_graph(relations, 'inferred_beautiful', f"{details['数据库']} Schema (Inferred)")
        except Exception as e:
            self._log(f"❌ 推断失败: {e}")
            self.after(100, lambda: messagebox.showerror("错误", f"推断失败:\n{e}"))
        finally:
            self.after(100, lambda: self._toggle_controls("normal"))


if __name__ == "__main__":
    app = RelationDiagramApp()
    app.mainloop()