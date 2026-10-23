# 视频学习笔记

把指定视频或本地音视频整理成可回查的学习笔记：先取得可信字幕或完整转录，再核对必要画面，保留来源、时间点和未解决的内容缺口。

## 适合什么任务

- 记录教程中的操作步骤、设置、代码和关键截图。
- 整理讲座、课程或访谈的主要概念、方法与案例。
- 从适合操作复用的视频中提炼工作流和完成条件。
- 对需要转录的长音轨保存检查点，中断后继续。

## 使用

安装整个 `video-to-note` 目录，安装方式见[仓库说明](../../README.md)。在 Agent 中说：

```text
使用 $video-to-note 读取【视频链接或本地文件】。
按章节整理学习笔记，核对关键操作画面，标注时间点，保存到【笔记目录】。
```

先确定所需单个视频或分 P。平台是否可访问、是否需要登录和字幕是否可信，以当次实际结果为准；安装下载器不代表一定取得材料。

## 环境与依赖

有可信字幕时可以先用字幕；需要转录时，使用 Python 3.10+、FFmpeg / FFprobe，以及 [requirements.txt](requirements.txt) 中的 `numpy`、`faster-whisper`、`PyYAML`。平台下载器、模型与登录态按任务另配。

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Get-Command ffmpeg,ffprobe
```

命令从本 Skill 目录执行。macOS / Linux 使用 `.venv/bin/python`。脚本不默认下载模型；首次转录需明确模型、先做一分钟试读。配置和命令详见[环境说明](references/local-environment.md)。

## 输出

- **Markdown 笔记**：来源、时长、实际处理范围、要点和关键时间点。
- **持久附件**：必要截图及笔记中的图片链接，不依赖临时目录。
- **同名 `.evidence.json`**：章节范围、关键证据、核对记录及未解决项。

中间媒体与转录检查点保存在独立任务目录。成功核对并确认持久文件可读后才清理，用户原文件和模型缓存保留。

## 文件入口

| 文件 | 用途 |
|---|---|
| [SKILL.md](SKILL.md) | Agent 的获取、核对、写作与清理流程 |
| [画面选择](references/frame-selection.md) | 定位关键画面，检查章节漏图 |
| [证据格式](references/evidence.md) | 保存来源、范围与核对结果 |
| [transcribe.py](scripts/transcribe.py) | 试转录、完整转录与断点续跑 |
| [finalize.py](scripts/finalize.py) | 检查证据与文件，按条件清理临时目录 |

## 限制

不会凭标题、简介或抽样片段声称总结了全片。语音识别会出错，低分辨率、遮挡、公式与专有名词可能需要人工回听或看图复核。

`transcribe.py` 处理完音轨不等于每句准确，`finalize.py` 通过也不等于内容已经语义核验。实际阅读、比对和笔记整理由宿主 Agent 完成。

本目录尚未附独立许可证；不自动沿用其他 Skill 的 MIT 授权。
