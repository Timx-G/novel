# 《不要怕》

**[在线阅读 PDF](不要怕/04-导出/不要怕-阅读样本-v0.2.pdf)** · **[下载 PDF](https://raw.githubusercontent.com/Timx-G/novel/main/不要怕/04-导出/不要怕-阅读样本-v0.2.pdf)**

当前阅读版共 5 页，包含封面、扉页、目录和第一篇正文 v0.3。点击上方即可阅读；如果 GitHub 预览未加载，或需要使用 PDF 内的目录跳转和引用链接，可下载后打开。下方是写作项目说明，阅读正文不需要查看 Markdown 文件。

一部持续写作中的真实故事与随笔集，首先写给现在与未来的自己。“不要怕”是面对经历、困难和挫折时，留给自己的提醒。

每天保存一份原始草稿，先一起讨论，再根据内容补充已有篇章或写成新篇。素材按日期积累，正文按主题组织；目前已有一篇初稿，其余篇目随材料推进。

## 阅读与接续

- [从这里开始](不要怕/开始这里.md)
- [第一篇：为什么要把这些写下来](不要怕/02-正文/为什么要把这些写下来.md)：正文 v0.3，仍为初稿。
- [PDF 阅读样本 v0.2](不要怕/04-导出/不要怕-阅读样本-v0.2.pdf)：5 页，包含封面、扉页、目录及正文。
- [全书目录](不要怕/00-全书规划/全书目录.md) · [协作记录](不要怕/00-全书规划/协作记录.md)
- [Mission](不要怕/specs/mission.md) · [表达方式](不要怕/specs/tech-stack.md) · [Roadmap](不要怕/specs/roadmap.md)

## 文件与版本

原始素材、正文与历史归档分别保存。素材包含尚待讨论、核对或修正的原始表达，篇章中的事实与最新决定以对应 Spec 和协作记录为依据。

公开仓库：[Timx-G/novel](https://github.com/Timx-G/novel)。2026-11-11 已将首轮写作分支合入 `main`，并公开推送主线和 `codex/why-write-spec` 专题分支。两条分支均保留，完整提交历史可以回看；合入不代表文章最终定稿。

仓库包含已跟踪的素材、正文、封面、PDF 样本、写作 Skill、Spec、协作记录与归档。未提交文件、临时文件和按提交自动生成的本机合入版不随 Git 推送；可直接阅读上方选定的 PDF 样本。

## 写作与排版

- [life-writing](.agents/skills/life-writing/SKILL.md)：整理想法、真实经历与已有文字，保留原始材料，逐篇修订。
- [book-reading-edition](.agents/skills/book-reading-edition/SKILL.md)：根据已收录正文生成阅读版；本地合入 `main` 后由 Git 钩子调用导出脚本，再检查排版。

新克隆需要在仓库根目录运行 `bash .agents/skills/book-reading-edition/scripts/install_hooks.sh` 接入本地钩子；字体与运行依赖见[阅读版说明](不要怕/specs/reading-edition.md)。远端推送不会启动本机助手或替代视觉检查。
