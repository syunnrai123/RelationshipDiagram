import pymysql
from graphviz import Digraph
import tkinter as tk
from tkinter import messagebox
import os
import re

# ===== Tkinter GUI 部分 (提前定义，方便函数调用) =====
root = tk.Tk()
root.title("MySQL 表关系图生成器")
root.geometry("400x350")  # 窗口加宽加高以容纳新按钮

tk.Label(root, text="主机:").pack()
entry_host = tk.Entry(root)
entry_host.insert(0, "localhost")
entry_host.pack()

tk.Label(root, text="端口:").pack()
entry_port = tk.Entry(root)
entry_port.insert(0, "3306")
entry_port.pack()

tk.Label(root, text="用户名:").pack()
entry_user = tk.Entry(root)
entry_user.insert(0, "root")
entry_user.pack()

tk.Label(root, text="密码:").pack()
entry_password = tk.Entry(root, show="*")
entry_password.pack()

tk.Label(root, text="数据库:").pack()
entry_database = tk.Entry(root)
entry_database.pack()


def get_connection():
    """从GUI获取信息并返回数据库连接"""
    host = entry_host.get()
    port = int(entry_port.get())
    user = entry_user.get()
    password = entry_password.get()
    database = entry_database.get()

    conn = pymysql.connect(
        host=host, port=port, user=user,
        password=password, database=database,
        cursorclass=pymysql.cursors.DictCursor  # 使用字典光标方便处理
    )
    return conn, database


def generate_diagram_by_fk():
    """
    原始功能：严格根据数据库中定义的外键 (Foreign Key) 生成关系图。
    """
    try:
        conn, database = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT table_name, referenced_table_name
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE table_schema = %s
          AND referenced_table_name IS NOT NULL
        """, (database,))

        dot = Digraph(comment=f'{database} Schema (FK based)', format="png")
        dot.attr('graph', label=f'{database} Schema (Based on Foreign Keys)', labelloc='t', fontsize='20')

        relations = set()
        for row in cur.fetchall():
            relations.add((row['table_name'], row['referenced_table_name']))

        if not relations:
            messagebox.showwarning("提示", "在数据库中没有找到任何外键关系。")
            return

        for table, ref_table in relations:
            dot.node(table, shape='box', style='rounded')
            dot.node(ref_table, shape='box', style='rounded')
            dot.edge(table, ref_table)

        output_file = os.path.join(os.getcwd(), "mysql_relation_fk")
        dot.render(output_file, cleanup=True)

        cur.close()
        conn.close()

        messagebox.showinfo("完成", f"✅ 已基于外键生成关系图:\n{output_file}.png")
    except Exception as e:
        messagebox.showerror("错误", str(e))


def generate_diagram_by_inference():
    """
    新功能：根据命名约定来推断 (Inference) 表关系。
    """
    try:
        conn, database = get_connection()
        cur = conn.cursor()

        # 1. 获取所有表的所有列信息，包括是否是主键
        cur.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, COLUMN_KEY 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s
        """, (database,))

        all_columns_info = cur.fetchall()

        tables = {}  # 用于存储每个表的列和主键信息
        for col in all_columns_info:
            table_name = col['TABLE_NAME']
            if table_name not in tables:
                tables[table_name] = {'columns': [], 'pk': None}
            tables[table_name]['columns'].append(col['COLUMN_NAME'])
            if col['COLUMN_KEY'] == 'PRI':
                tables[table_name]['pk'] = col['COLUMN_NAME']

        # 2. 开始推断关系
        relations = set()
        table_names = list(tables.keys())

        for table_name, table_info in tables.items():
            for column_name in table_info['columns']:
                # 规则：列名以 '_id' 结尾，且不是主键
                if column_name.endswith('_id') and column_name != table_info['pk']:
                    # 提取关联表名的前缀，例如 'user_id' -> 'user'
                    potential_ref_table_singular = column_name[:-3]

                    # 在所有表中查找可能的匹配
                    for target_table_name in table_names:
                        # 简单的单复数处理：'user' 应该匹配 'users'
                        if target_table_name.rstrip('s') == potential_ref_table_singular:
                            # 确认目标表的主键是'id' (最常见的情况)
                            if tables[target_table_name]['pk'] == 'id':
                                relations.add((table_name, target_table_name))
                                break  # 找到后就不用再找了

        if not relations:
            messagebox.showwarning("提示", "根据命名约定未能推断出任何关系。")
            return

        # 3. 使用 Graphviz 绘制
        dot = Digraph(comment=f'{database} Schema (Inferred)', format="png")
        dot.attr('graph', label=f'{database} Schema (Inferred by Convention)', labelloc='t', fontsize='20')

        for table, ref_table in relations:
            dot.node(table, shape='box', style='rounded')
            dot.node(ref_table, shape='box', style='rounded')
            dot.edge(table, ref_table, label='inferred')

        output_file = os.path.join(os.getcwd(), "mysql_relation_inferred")
        dot.render(output_file, cleanup=True)

        cur.close()
        conn.close()

        messagebox.showinfo("完成", f"✅ 已基于命名约定推断出关系图:\n{output_file}.png")
    except Exception as e:
        messagebox.showerror("错误", str(e))


# ===== 创建按钮并绑定函数 =====
tk.Button(root, text="1. 基于外键生成 (精确)", command=generate_diagram_by_fk).pack(pady=5)
tk.Button(root, text="2. 基于约定推断 (无外键时使用)", command=generate_diagram_by_inference).pack(pady=5)

# 启动 Tkinter 事件循环
root.mainloop()