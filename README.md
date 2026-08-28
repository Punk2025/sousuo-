# SearchPipe · 搜索网

本地「搜索管线 + 跳转手法研究」工具集：用 Playwright 搜百度出报表，可选打标识别跳转壳站 / 疑似成人 / 博彩；另附延迟跳转与站群中控教学演示。

> **定位**：研究、识别、报表。不是生产导流系统，请勿用于违法用途。

---

## 能做什么

| 能力 | 说明 |
|------|------|
| 百度 SERP 抓取 | 本机 Chromium（有界面）搜词，支持验证码人工过 |
| 批量 / 导入 | 多关键词排队；支持 `.txt` / `.csv` 导入 |
| 报表导出 | 名称 / 域名 / 分类 / 可点击链接 → HTML / CSV |
| 搜索记录 | 新搜索前自动归档上次结果，主面板只留本次 |
| 规则打标 | 跳转壳站、JS 延迟跳转、疑似成人、博彩、TG、USDT |
| 教学演示 | 延迟跳转 + 后退劫持前端 demo；跳转中控实验室 |

---

## 仓库结构

```text
.
├── pipeline/     # 核心：搜索管线后台（端口 8878）
├── demo/         # 前端：延迟跳转 → 落地 → 后退劫持
├── zhongkong/    # 跳转中控实验室（端口 8877）
└── docs/         # 技术笔记
```

| 目录 | 内容 |
|------|------|
| [`pipeline/`](./pipeline/) | Flask 控制面板 + Playwright 搜百度 + 打标入库 |
| [`demo/`](./demo/) | 单次访问链路演示 |
| [`zhongkong/`](./zhongkong/) | 批量入口 + 一键下发 `/jump.js` |
| [`docs/`](./docs/) | 手法拆解与开源对照 |

---

## 快速开始（搜索管线）

### Mac 一条命令安装（从 GitHub）

终端粘贴执行：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Punk2025/sousuo-/main/mac/bootstrap.sh)"
```

自动克隆到 `~/SearchPipe` 并完成安装。指定目录：`INSTALL_DIR=~/Desktop/搜索网` 加在前面。

### Mac 一键安装（已有项目文件夹）

1. 把项目文件夹拷到 Mac（或 `git clone`）
2. **双击 `Mac一键安装.command`**
3. 按提示操作（首次会装 Homebrew → Python → 依赖 → Chromium，可能要输入 Mac 密码）
4. 安装完成后桌面会出现 **`SearchPipe.command`**，以后双击它即可启动

控制面板地址：http://127.0.0.1:8878/admin/  
停止服务：在终端窗口按 `Ctrl+C`。

> 若提示「无法打开」：右键文件 → **打开** → 确认打开。

### 已安装后启动

| 方式 | 说明 |
|------|------|
| 桌面 `SearchPipe.command` | 安装时自动创建 |
| `启动SearchPipe.command` | 项目内启动器（安装后生成） |
| `一键运行.command` | 同上，快捷入口 |

### 终端启动（macOS / Linux）

```bash
chmod +x run.sh
./run.sh
```

### 主流程

1. **① 搜索**：单词 / 批量 / 导入 txt·csv → 出报表（默认不打标）  
2. **② 表格报表**：导出可点击 HTML 或 CSV  
3. **③ 后续处理**（可选）：并发打标；快速模式默认开启  
4. **搜索记录**：历史归档，可回看 / 下载 / 删除  

新搜索会清空当前工作区，上次结果自动进「搜索记录」。

**完整图文教程** → [`docs/使用教程.md`](./docs/使用教程.md)

### 打标说明（规则）

| 分类 | 依据（摘要） |
|------|----------------|
| 跳转壳站 / 客户端跳转 | 空壳特征 + `setTimeout` / `location` |
| 疑似成人 | 标题 / 页面关键词（成人直播、A片…） |
| 博彩内容站 | 开元、加拿大28、百家乐等 |
| 抓取失败·疑似成人 | 页面打不开时，仍按 SERP 标题补标 |
| TG / USDT | 落地文案信号 |

详情见 [`pipeline/README.md`](./pipeline/README.md) 与 [`docs/搜索管线-SERP报表与打标.md`](./docs/搜索管线-SERP报表与打标.md)。

---

## 其它模块

### 前端链路演示

```bash
cd demo
python3 -m http.server 8765
# http://127.0.0.1:8765/
```

### 跳转中控

```bash
cd zhongkong
python3 server.py
# http://127.0.0.1:8877/admin/
```

### 文档

1. [**使用教程（Mac 一键安装 + 完整流程）**](./docs/使用教程.md)  
2. [客户端延迟跳转与历史劫持](./docs/客户端延迟跳转与历史劫持.md)  
3. [站群跳转中控](./docs/站群跳转中控.md)  
4. [搜索管线 · SERP 报表与打标](./docs/搜索管线-SERP报表与打标.md)  
5. [相关开源与资料](./docs/相关开源与资料.md)  

---

## 设计取舍

- **先报表，后打标**：百度 SERP 不稳定时，不把深抓和搜索绑死。  
- **浏览器必须能跑起来**：本机 Playwright；Cloudflare Workers 不能直接替代（可用 CF Browser Run，但验证码不如本机有界面方便）。  
- **运行数据不进仓库**：`pipeline/data/` 下工作 CSV、历史归档、浏览器配置、SQLite 已在 `.gitignore` 中忽略。

---

## 技术栈

- Python · Flask · Playwright · httpx · BeautifulSoup · SQLite  
- 前端：原生 HTML/CSS/JS（控制面板为卡通苹果浅色 UI）

---

## License / 声明

教学与安全研究用途。使用者自行遵守当地法律法规；作者不对滥用行为负责。
