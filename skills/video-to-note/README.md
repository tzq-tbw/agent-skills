# video-to-note

Codex视频学习笔记Skill，版本 **2.1.0**。

读取视频链接或本地音视频，结合字幕、完整音轨转录与关键画面生成可追溯的图文笔记。需要时提炼工作流与提示词，区分作者做法和整理建议。

## 新版关键画面规则

有章节时按章节读取；章节不可取得时，用主题转换与标题页建立“分析者划分”。结合正文变化、讲解信息点及15—30秒概览采样定位候选图，比较相邻帧，选完整、稳定、遮挡少的画面。

优先保留清单、步骤、设置、代码、公式、对比和操作结果；相似画面有独有信息时不去重。截图数量不预设，最终逐节检查漏图，保存时间、用途与跳过理由。

## 安装与依赖

这是Skill仓库，不是独立桌面应用。把仓库放在Codex技能目录的`video-to-note`文件夹中，保证`SKILL.md`位于根目录。

目标目录不存在时，可执行：

```powershell
git clone https://github.com/tzq-tbw/agent-skills.git
Copy-Item -LiteralPath .\agent-skills\skills\video-to-note -Destination "$env:USERPROFILE\.codex\skills\video-to-note" -Recurse
```

已有同名Skill时先备份再更新，不重复安装到多个发现目录。重启Codex或新建会话后检查技能列表。

转录需要Python、FFmpeg/FFprobe及`requirements.txt`里的包。配置与运行命令见[环境说明](references/local-environment.md)。下载器、平台登录和模型按实际来源另配；工具可用性以当次结果为准。

## 使用

在Codex聊天中说：

```text
使用 $video-to-note 读取【视频链接或本地文件路径】，生成图文学习笔记。
按章节和独有信息选取关键截图，注明时间与用途，保存到【笔记目录】。
适合操作复用时补充工作流，区分作者做法和整理建议。
```

Codex执行工具、阅读转录、核对画面并整理笔记。`transcribe.py`只转录；`finalize.py`只检查证据记录与文件，不能替代语义审阅。

## 文件

- `SKILL.md`：执行入口。
- `references/frame-selection.md`：关键画面选择与漏图检查。
- `references/evidence.md`：持久证据格式。
- `references/local-environment.md`：环境与命令。
- `scripts/transcribe.py`：试读、完整转录与断点续跑。
- `scripts/finalize.py`：产出检查和成功清理。
- `scripts/test_helpers.py`：辅助脚本的隔离检查。

转录完成不代表每句准确；原视频遮挡与低分辨率仍可能需人工复核。仓库不包含用户视频、笔记、模型缓存或登录凭据。
