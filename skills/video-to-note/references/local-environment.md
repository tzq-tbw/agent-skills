# 环境配置与执行命令

发布版使用通用配置。执行前检查当前机器的解释器、FFmpeg、下载工具和笔记目录，不沿用其他机器的路径。

## 依赖

- Python 3.10或更新版本；`numpy`、`faster-whisper`；格式校验需要`PyYAML`。
- FFmpeg和FFprobe在当前进程PATH中。
- 按平台另配下载器：YouTube可用`yt-dlp`；B站用已配置的`bili-cli`或其他已授权工具。安装成功不代表当次下载可用。
- 用户指定笔记目录；有现成Obsidian时使用其视频笔记目录，否则保存到工作区`outputs/`。

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r <skill_dir>\requirements.txt
# 需要YouTube下载时另装：
& .\.venv\Scripts\python.exe -m pip install yt-dlp
Get-Command ffmpeg,ffprobe
```

macOS/Linux使用`.venv/bin/python`。FFmpeg从系统包管理器或官方发行包安装。

## 转录

替换`<skill_dir>`与`<media_path>`为当前实际绝对路径：

```powershell
$videoPython = (Resolve-Path '.venv\Scripts\python.exe').Path
$skillDir = '<skill_dir>'
$taskDir = Join-Path (Get-Location).Path ('work\video_tmp\' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskDir -ErrorAction Stop | Out-Null
$mediaPath = '<media_path>'
& $videoPython -X utf8 "$skillDir\scripts\transcribe.py" $mediaPath --task-dir $taskDir --model medium --pilot
# 阅读并核对试转录后继续：
& $videoPython -X utf8 "$skillDir\scripts\transcribe.py" $mediaPath --task-dir $taskDir --model medium
```

默认只加载已缓存模型。首次使用且确需下载时加`--download-model`，需网络和存储。根据试读质量、速度选择small或medium，不静默换模型。来源、模型、语言改变时新建任务目录。

脚本标准化为16 kHz单声道PCM16，以NumPy数组传给识别器，避免直接用PyAV读取路径的兼容问题。一分钟检查点用于续跑，不证明文本逐句准确。

用户原文件只读。下载媒体与临时截图放进任务目录；模型缓存、持久笔记与附件放在目录外。

## 产出检查和清理

```powershell
$notePath = '<durable_note_path>'
$evidencePath = '<durable_evidence_json_path>'
& $videoPython -X utf8 "$skillDir\scripts\finalize.py" --workspace (Get-Location).Path --task-dir $taskDir --note $notePath --evidence $evidencePath
```

语义核对、回读与附件检查完成后，才运行相同命令加`--clean`。脚本只允许清理工作区`work/video_tmp`中的一个直接子目录，拒绝符号链接与重解析点；原文件、模型和持久产出不删。

修改辅助脚本时可运行`python scripts/test_helpers.py`，它检查续跑、安全清理，不证明具体视频的识别准确率。格式校验使用Codex自带`skill-creator/scripts/quick_validate.py`，需定位其实际路径。
