# excel-to-sql

中文 | [English](README.en.md)

单机桌面工具（macOS / Windows）：导入 Excel/CSV → SQLite 数据库，内置数据浏览与条件搜索。设计方案见 [plan.md](plan.md)。

## 功能

- **多文件 / 多 Sheet 勾选批量导入**，空表、空行自动跳过
- **类型自动推断**：INTEGER / REAL / TEXT / 日期（ISO8601），导入前可逐列修改列名与类型；超 2^53 长编号自动按文本保留精度
- **条件搜索**：等于 / 不等于 / 包含 / 不包含 / 局部匹配（`*` 任意多字符、`?` 单字符），中文直接可用；每个条件的值可逗号分隔多个（等于/包含/局部匹配=命中任一，不等于/不包含=全部排除），多行条件 且/或 组合；搜索结果在独立标签页展示，可保留多个结果对比
- **目录树与范围搜索**：左侧"大表（Excel 文件）▸ 子表"两级目录，勾选子表即搜索范围（可跨大表）；支持正向（勾选范围）/反向（未勾选范围）查找；**跨表查找会预先校验所选子表表头结构是否一致（列名+类型），不一致则提示差异并拒绝**；范围结果按子表汇总命中数并联动明细；拖动或右键菜单可移动子表到大表、重命名大表（仅改目录归属，不动数据）；全选/全不选/反选一键调整范围
- 结果导出 Excel / CSV（UTF-8 BOM，双平台 Excel 打开不乱码）
- 同名表策略：覆盖 / 重命名 / 追加；GBK 编码 CSV 自动嗅探

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# GUI（导入向导 + 数据浏览与搜索）
python main.py

# 命令行（自动化 / 测试通道）
python scripts/make_samples.py                                 # 生成示例 Excel
python cli.py convert samples/订单示例.xlsx -o output/demo.db   # 导入
python cli.py tables -d output/demo.db                         # 列出表
python cli.py search -d output/demo.db -t 订单表 --where 商品名称~手机
python cli.py export -d output/demo.db -t 订单表 -o output/订单表.xlsx
```

CLI 条件语法：`列名=值`（等于）、`列名!=值`（不等于）、`列名~值`（包含）、`列名!~值`（不包含）、`列名@模式`（局部匹配，`*`/`?` 通配）。含 `*` 的条件记得加引号，避免被 shell 展开。

## 测试

```bash
python -m pytest tests/ -q                        # 单元 + 集成（33 项）
QT_QPA_PLATFORM=offscreen python scripts/smoke_gui.py   # GUI 离屏冒烟
```

## 目录结构

```
app/core/     核心引擎：excel_reader / type_inference / schema_builder /
              sqlite_writer / query_builder / db_browser（与 UI 解耦，可独立测试）
app/models/   TableMeta / ColumnMeta
app/ui/       主窗口（浏览+搜索）、三步导入向导、数据表格控件
cli.py        命令行入口；main.py GUI 入口
tests/        pytest；scripts/ 示例生成与 GUI 冒烟
```
