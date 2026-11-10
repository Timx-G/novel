# 本地合入与阅读版

## 两层接入

`AGENTS.md` 指引协作助手使用 skill；Git 的 `core.hooksPath=.githooks` 负责事件触发。仅写 Markdown 不会让任意 Git 操作启动模型。这里自动运行排版程序，助手负责视觉检查与报告。

| 本地操作 | 实际行为 |
| --- | --- |
| main 成功普通合并、快进合并或 pull 的 merge | `post-merge` 导出新 HEAD |
| squash 合并 | 准备时不导出；实际提交后 `post-commit` 导出 |
| 合并有冲突 | 不更新；解决后实际提交时导出 |
| main 直接 commit 或 amend | 提交或重写后导出；相同输入与提交可复用已有 PDF |
| main rebase | 完成后 `post-rewrite` 导出；失败中途不声称成功 |
| 功能分支提交、仅切换分支 | 不自动导出；使用预览命令 |
| 远端网页合并、另一台机器 | 不直接触发本机钩子；在该环境安装钩子并本地更新，或手动按提交导出 |

钩子只监听 `main`。项目配置路径是 `不要怕/specs/reading-edition.json`；迁移到其他书籍时调整公共钩子入口。新克隆需要重新安装钩子，仓库配置不随提交传播。Git reset 或绕过钩子的工具不保证触发，可手动补生成。

## 结果与失败

- `04-导出/合入版/<书名>-<提交号前12位>.pdf` 与同名 JSON：对应提交的阅读版和来源证据。
- `latest.json`：最近成功结果，不承诺始终对应 HEAD；核对 `source_revision`。
- 当前 Git 目录下 `book-reading/last-run.json`、`last-run.log`：最近触发结果和错误。用 `git rev-parse --absolute-git-dir` 定位当前工作树的 Git 目录。
- 失败不删除旧版、不回退 Git、不自动修复或提交正文。post 钩子发生时 Git 操作已完成，分别报告“合并成功、导出失败”；修复后按 skill 的 `--mode merged --revision main` 补生成。
- 自动版本目录与 `tmp/pdfs` 被忽略，不递归触发提交；明确选定的分支样本可以随项目保存。

## 本机依赖与版式

运行器优先使用 `BOOK_READING_PYTHON`，否则使用 Codex 已有 bundled Python，再回退 `python3`。需要 `reportlab`、`pypdf`、`pdfplumber`；缺失时失败并说明，不在 Git 操作中安装依赖或联网。

当前配置使用 macOS 宋体 TTC（简体常规 index 6、粗体 index 1），以子集嵌入 PDF。换机器时核对字体位置、字重索引和字形覆盖。视觉检查需要 PDF 渲染器，例如 `pdftoppm`。

配置为 140×210 mm、正文 11 pt、页边距 18 mm。封面、扉页不印页码，目录使用罗马数字，正文从 1 开始；按目录行序添加章号。封面按页面铺满；换不同比例图片时先调整版式，不默许拉伸。

事件语义依据 [Git hooks](https://git-scm.com/docs/githooks)，配置依据 [Git config](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corehooksPath)。
