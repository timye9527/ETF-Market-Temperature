# Prompt — 2026-10-06 轻量级 GitHub 资产化

> Owner 原文，逐字保存。已作为 Amendment A1 合并进 `MASTER_PROMPT.md`。

---

现在先暂停一下后续开发，对当前项目做一个轻量级 GitHub 资产化。

目标很简单：

把目前 ETF Market Temperature 项目已经产生的有效资产保存到我自己的 GitHub，形成第一个可持续开发的版本。

请执行：

1. 检查当前项目目录和已有文件。

2. 确保目前有价值的内容都进入项目目录，包括：
   - 当前代码
   - ETF taxonomy
   - ETF universe / metadata
   - Temperature 模型设计
   - 当前使用的核心 Prompt
   - 已经形成的研究/设计文档
   - 必要的配置模板

3. 建立或简单更新 README.md，只需要写清楚：
   - 这个项目是做什么的
   - 当前已经完成什么
   - 当前还在开发什么
   - 下一步准备做什么

不要现在花大量时间写复杂文档。

4. 把当前核心 Prompt 保存到：
   prompts/MASTER_PROMPT.md

后续重要 Prompt 也尽量保存在 prompts/ 目录，不要只存在 Claude 对话中。

5. 检查 .gitignore，确保：
   - API Key
   - Token
   - Password
   - .env
   - 本地敏感配置
   不会上传 GitHub。

6. 如果当前目录还没有 Git repository，则初始化 Git。

如果已经存在 Git repository，则沿用现有 repo，不要重复创建。

7. 检查 GitHub remote。

如果还没有对应 GitHub repository：
创建一个新的 repository，建议名称：

etf-market-temperature

如果已有对应 repository，则直接使用。

8. 将当前成果：

git add
git commit
git push

形成第一个正式 checkpoint。

Commit message 可以使用：

feat: initialize ETF Market Temperature project

9. 如果 push 成功，最后告诉我：

- GitHub repo
- branch
- commit hash
- 本次保存了哪些核心资产
- 是否还有重要内容只存在 Claude 对话、尚未进入 GitHub

完成以后继续回到产品开发。

暂时不要花时间建立复杂的灾难恢复体系、CHANGELOG、版本 Tag 或大量管理文档。

现阶段原则：

开发优先，
GitHub 持续沉淀，
重要成果及时 commit/push。

GitHub 是项目资产的长期载体，
Claude Code 负责继续开发。

---

## 同日后续指令（摘要）

- 本次只开发 ETF-Market-Temperature。不要修改 AI-supply-chain，不要把 ETF 项目的文件写入 AI-supply-chain，也不要合并两个 repository。
- 所有 ETF Market Temperature 的开发、commit 和 push 都只发生在 ETF-Market-Temperature repository。
