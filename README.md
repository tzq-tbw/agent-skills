# Agent Skills

可独立安装的学习辅助 Skill。此仓库仅包含技能指令、运行脚本、模板、资源和使用参考，不含个人学习记录、课件、密钥或原开发仓库提交历史。

| 目录 | 功能 |
|---|---|
| `skills/universal-exam-cram-coach` | 轻量备考、章节讲解、刷题、模拟卷、学习笔记和错题记录 |
| `skills/universal-exam-cram-coach-full` | 完整备考控制层、资料处理、题库、错题复习、知识混淆跟踪及学习指南 |
| `skills/video-to-note` | 视频字幕、音轨转录与关键画面核对，整理可追溯笔记 |

## 安装

克隆仓库，将需要的一个完整 Skill 目录复制到你的 Agent 技能目录，例如 Windows 上的 `%USERPROFILE%\.codex\skills\`。保留目录内全部文件及相对结构；不要单独复制完整版本的内部子技能。

```powershell
git clone https://github.com/tzq-tbw/agent-skills.git
Copy-Item -LiteralPath .\agent-skills\skills\universal-exam-cram-coach -Destination "$env:USERPROFILE\.codex\skills\universal-exam-cram-coach" -Recurse
```

目标目录已存在时先备份，避免直接覆盖。轻量版与完整版功能有重合，按任务选择安装。各 Skill 的入口为其目录中的 `SKILL.md`；具体依赖和执行方式以对应说明为准。

## 来源与许可证

保留原有作者署名与各 Skill 自带的许可证。备考助手的原作者署名为 ZeKaiNie，许可证见其目录中的 `LICENSE`。视频笔记目录未附独立 LICENSE，本次不新增或推定其授权条款。

后续修改请使用 GitHub noreply 提交邮箱；真实凭据和个人材料留在技能目录外。
