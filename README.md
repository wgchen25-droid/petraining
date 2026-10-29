# PE Training Radar · 欧洲电力电子培训雷达

专为欧洲尤其是德国电力电子研发人员制作的培训聚合站。基于 **18 个官方渠道**，初始收录 **47 门有明确日期的课程 / Webinar / Workshop**，并在此仓库中自动更新数据和发布静态主页。

## 功能

- 面向中文用户的响应式仪表盘；按技术主题、地区、授课形式、价格、日期进行筛选。
- 支持全文搜索、收藏（仅存在本地浏览器）、近期培训日历、课程方向统计、一键导出 CSV。
- 每条课程含官方来源链接和核实日期；不清楚的费用标记为「价格待询」，不会擅自显示「免费」。
- 18 个来源全量执行 **每周网页可达性与内容变更检查**；其中 8 个有结构化课程自动提取逻辑，另外 10 个属于监控型源，发现内容变化后可继续扩展专用解析器。
- 课程数据存储在 `data/courses.json`，来源目录在 `data/sources.json`；不需要服务器和数据库。

## 网站如何上线

仓库地址：**https://github.com/wgchen25-droid/petraining**

预期 GitHub Pages 地址：**https://wgchen25-droid.github.io/petraining/**（只有成功启用部署后才可访问）。

在 GitHub 仓库：

1. 前往 **Settings → Pages → Build and deployment**，选择 **GitHub Actions** 作为 Source。
2. 前往 **Actions → Collect weekly & publish training radar → Run workflow**，手动触发第一次部署。
3. 运行完成后，在 Actions 工作流结果和 Settings → Pages 查看实际公开地址。

**注意：仓库初始为 Private。** GitHub Free 仅支持从 Public 仓库部署 GitHub Pages；GitHub Pro / Team / Enterprise 支持 Private 仓库。若用户账户不支持 Private Pages，则需要由仓库管理员自行改为 Public 或升级相应 GitHub 计划。页面包含的培训信息全部来自公开官网，但更改仓库可见性前请自行确认没有私密内容。

## 自动化机制

`.github/workflows/weekly.yml`：

- 每周一 **06:17 UTC**（德国冬令时 07:17，夏令时 08:17）由 GitHub Actions 自动触发。
- 同时支持 `workflow_dispatch` 手动执行和推送源代码时重新部署。
- 安装 `requests`、`beautifulsoup4`，先执行单元测试，再遍历所有来源官网。
- 对于可提取课程的来源：只收录存在明确日期、标题且内容与电力电子相关的活动。
- 对于监控型来源：保存检查日期、成功/受限状态、页面内容哈希、是否有变化；不会假装自动获取具体课程。
- 过滤很久以前的课程，同一来源+课程+日期去重。部分网站如果拒绝访问，会保留上次核实课程而不是清空数据。
- 至少一个来源成功访问后生成最新 `courses.json`，自动提交到 `main` 并部署静态页面；完全失败时不会冒充更新成功。

GitHub 官方调度偶尔会延迟；网站改版、反爬或日期格式变化会导致某些课程无法被提取。监控结果不等于核实报名状态。务必点击官方链接确认费用、席位、时间与取消规则。

## 本地测试

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/collect.py --dry-run --only ecpe cluster biricha
python -m http.server 8000
```

打开 `http://localhost:8000/`。直接双击 `index.html` 可能无法通过浏览器的本地文件安全限制读取 JSON。

## 源文件说明

| 文件 | 用途 |
| --- | --- |
| `index.html` | 无框架单页网站，CSS / JS 内嵌、轻量可部署 |
| `data/sources.json` | 18 个官网及分类、监控模式 |
| `data/courses.json` | 初始官方课程 + 每周采集结果与状态 |
| `scripts/collect.py` | 日期解析、分类、去重、监控、数据更新 |
| `tests/test_collect.py` | 解析器和数据健全性测试 |
| `.github/workflows/weekly.yml` | 每周自动采集、Git 提交与 GitHub Pages 发布 |

## 扩展更多网站

在 `data/sources.json` 中添加合法公开课程 URL 和独一无二的 `id`；默认将 `collection` 设为 `watch` 仅监测页面变化。针对页面结构研究并测试解析规则后，方可改为 `structured`。采集器只使用公开网页、不绕过登录、不会复制视频/课件。

## 数据范围

初始来源于 2026-10-29 访问到的官方培训列表；后续更新取决于站点可达性。部分课程虽在合作主办方官网同时出现，只计入一个主来源以避免重复。项目不代表任何机构或官方认证。