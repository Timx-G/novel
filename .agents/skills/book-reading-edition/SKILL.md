---
name: book-reading-edition
description: "Use when a Markdown book needs a PDF reading preview with its chosen cover, title page, contents and page numbers, or when an authorized book integration into main needs a refreshed reading edition（书稿排版、阅读版、章节合入后导出）. Not for drafting or rewriting the manuscript."
---

# 书籍阅读版排版与导出

把已经写出的正文编排成 PDF。新增章节、修改旧章、调整目录或更换封面后，都从同一份 Markdown 来源重新生成。写作与事实修订交给 `life-writing` 和章节 Spec；排版不改写正文。

## 确认来源

1. 读取项目与书籍 `AGENTS.md`、目录及本书 `specs/reading-edition.json`。查看 Git 分支和工作区状态。
2. 目录中阅读顺序为“—”且备注“暂时撤下”的条目先排除，撤下不改变稿件成熟度。其余只收录“篇目清单”中状态为“初稿、修改中、暂定稿”且链接到 `02-正文` 的真实文章，按表格行序排列。待写篇目、素材、模板与归档不计入作品。调整顺序时同步移动目录行。
3. 沿用已选封面和配置，不虚构署名、出版信息或新篇章。稿件问题与排版检查分别报告；输出成功不代表内容已获作者认可。
4. 分支预览读取当前工作区；合入版读取指定 Git 提交中的封面、配置、目录和正文，排除未提交的稿件修改。导出不授权合并；用户要求不合入时保留当前分支。

## 生成预览

在仓库根目录运行，替换书籍路径与输出名；配置固定放在书籍的 `specs` 下。可通过文件入口使用，也可显式调用 `$book-reading-edition`。

```sh
bash .agents/skills/book-reading-edition/scripts/run.sh \
  --repo "$PWD" --config '不要怕/specs/reading-edition.json' \
  --mode preview --output "$PWD/不要怕/04-导出/不要怕-阅读样本-v0.1.pdf"
```

预览必须指定输出路径，已有阶段样本按项目约定保留或另取版本名。脚本生成 PDF 与同名 JSON，记录输入散列、基准提交、篇目、页码和检查结果。只有素材或空目录时停止，不补造内容。

支持普通段落、二三级小标题、加粗、网页链接和章末注。遇到复杂 Markdown、缺失正文或字体字符时明确失败；先扩展排版支持，不静默删掉内容。

## 合入后的自动导出

项目首次启用时运行安装器，只配置当前仓库；发现其他钩子时保留原配置，先协调接入。

```sh
bash .agents/skills/book-reading-edition/scripts/install_hooks.sh
```

本项目 `.githooks` 在本地 `main` 成功合并、提交或重写后调用此 skill 的导出脚本。自动化运行确定性脚本，不会自行启动 AI 对话；助手处理每次获授权合入时仍须读取此 skill、核对结果并完成视觉检查。触发范围、失败重试和新环境配置见[自动导出说明](references/automation.md)。

手动补生成某个已经存在的提交：

```sh
bash .agents/skills/book-reading-edition/scripts/run.sh \
  --repo "$PWD" --config '不要怕/specs/reading-edition.json' \
  --mode merged --revision main
```

合入版放入书内 `04-导出/合入版/`，按提交号保存；`latest.json` 指向最近成功版本。失败保留旧版并明确报告，不能把旧 PDF 当成最新版本。自动产物不提交 Git，不自动修改正文、提交或合并分支。

## 检查与交付

1. 核对 JSON 的提交、篇目和输入与本轮范围一致。脚本检查全文提取、跨页完整性、页面边界、目录导航和页码。
2. 将最终 PDF 渲染为图片，逐页检查封面比例、中文字体、标点换行、目录跳转目标、空白、注释和页码。修改排版后重新检查最终文件。
3. 自动导出默认 `visual_review: pending`。只有实际检查最终 PDF 全部页面，才能在同名 JSON 记录结果、日期和 PDF SHA256；当前合入版还需同步 `latest.json`。无人检查的自动版本如实保留待检查状态。
4. 交付 PDF 入口，说明收录篇目、版本和未完成核验；必要进度写回书籍阅读版 Spec 和协作记录。排版不提升章节成熟度。

使用具有上述依赖的 Python 运行 `scripts/test_export.py`，可在临时仓库验证 Git 触发与真实 PDF。不要为验证合并作者的实际分支。
