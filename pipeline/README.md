# 搜索管线（两段式）

应对百度 SERP 不稳定：**先导出排名网址报表，再离线处理**。

```text
阶段 A  多关键词排名 URL → CSV/Excel 报表（可手工复制）
阶段 B  读 CSV → 抓取/跟跳转 → 规则打标 → SQLite/MySQL
```

## 后台控制面板（推荐）

```bash
cd pipeline
pip install -r requirements.txt flask
python3 server.py
# 打开 http://127.0.0.1:8878/admin/
```

面板主流程（**先报表，后其它**）：
1. 单词/批量搜索百度 → 生成报表  
2. 在「表格报表」导出 HTML / CSV（名称、域名、分类、可点击链接）  
3. 需要时再去「后续处理」做跳转/博彩打标  

默认**不**自动打标。进度条显示「词 2/5」。验证码在弹出的 Chromium 里点一次即可。

## 命令行试跑（阶段 B）

```bash
cd pipeline
pip install -r requirements.txt
python3 phase_b_process.py --csv data/serp_sample.csv
```

示例 CSV 里包含此前拆过的跳转壳站 + 正常对照站。跑完后：

```bash
sqlite3 data/pipeline.db "SELECT keyword, rank_no, page_type, is_js_redirect, has_gambling, final_url FROM serp_results;"
```

可选导出 JSON：

```bash
python3 phase_b_process.py --json-out data/out.json
```

若已安装 Crawl4AI，可加：

```bash
python3 phase_b_process.py --crawl4ai
```

未安装时自动用 `httpx` 静态分析外链 JS（对「壳页 + setTimeout + location」同样有效）。

## 阶段 A：报表格式

模板：`data/serp_sample.csv` / `data/serp_template.csv`

| 列 | 说明 |
|----|------|
| keyword | 搜索词，如加拿大28 |
| rank | 百度排名位次 |
| url | 结果网址 |
| title | 标题（可选） |
| fetched_at | 采集日期（可选） |

从百度复制结果时，按此表填或导出即可，**不必**和阶段 B 同时在线打百度。

## MySQL

默认先用 SQLite 方便本机试。有 MySQL 时执行 `schema.sql`，后续可把 `phase_b_process.py` 的写入换成 PyMySQL（字段已对齐）。

## 打标说明

当前为**规则优先**（可后续接 LLM）：

- `跳转壳站`：空壳/加载中 + 外链脚本里 `setTimeout`/`location`
- `是否博彩` / `TG` / `USDT`：落地页与正文关键词
- `证据` 字段保留 jump 脚本 URL、是否含后退劫持等

目标 JSON 形态：

```json
{
  "类型": "跳转壳站",
  "标签": ["JS延迟跳转", "入口壳站", "博彩"],
  "是否TG": false,
  "是否USDT": false,
  "是否博彩": true
}
```
