# Learning Skills · 学习助手

三个独立的学习 Skill：课程备考、错题整理与互动复习、视频学习笔记。每个目录包含 Agent 的 `SKILL.md` 入口和运行所需文件；它们不是独立桌面应用。

## 选择一个 Skill

| Skill | 适合的任务 | 使用说明 | Agent 入口 |
|---|---|---|---|
| 备考助手 | 用课件、作业和真题分章学习、练习、记错题，按需制作模拟卷与讲义 | [README](skills/universal-exam-cram-coach/README.md) | [SKILL.md](skills/universal-exam-cram-coach/SKILL.md) |
| 错题整理与分析 | 按小节分析图片、扫描页、PDF 或文字错题，先预览再确认归档，逐问复习并记录掌握情况 | [README](skills/mistake-review/README.md) | [SKILL.md](skills/mistake-review/SKILL.md) |
| 视频学习笔记 | 根据字幕、完整转录与必要画面整理笔记，保留来源和关键时间点 | [README](skills/video-to-note/README.md) | [SKILL.md](skills/video-to-note/SKILL.md) |

## 安装

把选中的整个 Skill 目录放进当前 Agent 识别的技能目录，不要只复制 `SKILL.md`。以下是 Windows 上复制到 Codex 用户技能目录的示例；已有目标目录时停止，先备份后再选择更新方式。

```powershell
git clone https://github.com/tzq-tbw/agent-skills.git
$skillName = 'mistake-review'
$skillSource = Join-Path '.\agent-skills\skills' $skillName
$skillTarget = Join-Path $env:USERPROFILE ".codex\skills\$skillName"
if (Test-Path -LiteralPath $skillTarget) { throw '目标已存在，请先备份。' }
New-Item -ItemType Directory -Force -Path (Split-Path $skillTarget) | Out-Null
Copy-Item -LiteralPath $skillSource -Destination $skillTarget -Recurse
```

将 `$skillName` 换为其他目录名即可选择相应 Skill。其他 Agent 使用其实际支持的技能目录。安装后重启或新建会话，确认技能已被发现。

## 使用示例

```text
使用 $universal-exam-cram-coach。
资料在【课程目录】，还有 3 天考试，先列出章节，再从第一章开始。
```

```text
使用 $mistake-review。
把这些错题整理到【学科／章节／小节】，库放在【错题库目录】。
先给分析预览，我确认后再归档；以后基于已有分析逐问复习。
```

```text
使用 $video-to-note 读取【视频链接或本地文件】。
整理学习笔记，核对关键操作画面，注明时间点，保存到【笔记目录】。
```

## 环境与输出

| Skill | 环境 | 主要输出 |
|---|---|---|
| 备考助手 | Python 3.8+；PDF 提取和裁图按需使用 `pypdfium2` | 课程进度、练习与错题、笔记、小抄，按需生成模拟卷或讲义 |
| 错题整理与分析 | Python 3，建议 3.10+；`pypdf`、Tectonic 或 XeLaTeX，以及 PDF 页面渲染工具按任务配置 | 按小节保存的 Markdown、LaTeX、PDF、复习记录与配图 |
| 视频学习笔记 | Python 3.10+；转录时需要 FFmpeg / FFprobe、`numpy`、`faster-whisper`、`PyYAML` 及可用模型 | Markdown 笔记、持久截图、来源和核对证据 |

转录下载器、模型、文档编译器和宿主工具能力按实际任务检查。错题 Skill 不附编译器二进制，不携带个人错题库。Skill 的识图、解题、讲解与内容核对由 Agent 完成，脚本不自动保证答案或识别准确。

## 文件说明

`SKILL.md` 负责场景与执行流程，`README.md` 面向使用者；`scripts/`、`coach/`、`references/` 和 `agents/` 按各自功能提供工具、参考与显示信息。文件数量不等于 Skill 数量。

个人资料、错题库、媒体、输出与密钥应放在独立工作区。错题未确认时不写正式库，实际错因不清楚时标记待确认，复习记录不冒充真实学习情况。

## 来源与许可证

备考助手保留原作者 `ZeKaiNie` 的署名，许可证为 [MIT](skills/universal-exam-cram-coach/LICENSE)。错题整理与视频笔记目录尚未附独立许可证，不自动沿用其他目录的 MIT 授权。

各 Agent 的技能发现、工具执行和图片展示能力不同，安装成功不等于已通过全部教学、转录或 PDF 排版验收。
