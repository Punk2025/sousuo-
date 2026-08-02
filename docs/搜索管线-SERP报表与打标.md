# 搜索管线：SERP 报表 → 打标入库

> 记录日期：2026-08-03  
> 代码：`pipeline/`

## 为什么两段式

百度 SERP（验证码、反爬）不稳定时，不要和深抓绑在同一趟任务里。

```text
阶段 A  批量扫关键词排名 → 复制/下载成 CSV 报表
阶段 B  读报表 → 抓取跟跳转 → 规则/LLM 打标 → SQLite 或 MySQL
```

## 阶段 A 字段

见 `pipeline/data/serp_template.csv`：`keyword,rank,url,title,fetched_at`。

## 阶段 B

```bash
cd pipeline
python3 phase_b_process.py --csv data/serp_sample.csv
```

- 默认 `httpx` 静态解析外链 JS（壳页 + `setTimeout` + `location`）
- 已装 Crawl4AI 时加 `--crawl4ai`
- 默认写入 `data/pipeline.db`；MySQL 表结构见 `schema.sql`

## 示例跑通结果

对 `http://www.blog.wdgxlsu.com/`：

- 类型：跳转壳站  
- 最终页：`http://qs88.hbedwde.cn/12.html`  
- 标签：JS延迟跳转、入口壳站、后退劫持、博彩  

对照站 `example.com` 判为普通站。
