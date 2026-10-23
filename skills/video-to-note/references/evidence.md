# 持久内容证据

证据 JSON 与笔记放在临时目录外。保留支持关键总结的简短原文/转录片段和画面引用；原始识别有噪声时同时说明核对方式，不能把猜测写成引文。

下面示范一个60秒材料的结构；时间和内容必须来自实际材料。`material.completed` 是处理范围状态，`review.passed` 是你逐章阅读与核对后的结论，两者不能互相替代。

```json
{
  "source": "https://www.bilibili.com/video/BV1cV3b67Ehs",
  "duration_seconds": 60,
  "material": {"kind": "asr", "completed": true},
  "chapters": [
    {
      "start": 0,
      "end": 60,
      "reviewed": true,
      "evidence": [
        {"time": 12, "excerpt": "与笔记主要结论对应的实际短片段", "checked_by": "audio"}
      ]
    }
  ],
  "key_details": [
    {
      "detail": "需要核对的工具名称、数值或操作步骤",
      "verified": true,
      "evidence": {"time": 35, "image": "附件/关键页面.jpg", "checked_by": "frame"}
    }
  ],
  "review": {"passed": true, "unresolved_gaps": []},
  "attachments": ["附件/关键页面.jpg"]
}
```

材料类型：`subtitles`（独立字幕）、`asr`（完整音轨转录）、`burned-subtitles`（画面字幕）、`visual`（完整视觉阅读）。混合材料时选主要类型，并在笔记和证据片段中说明辅助手段。

各章覆盖选中的时间范围；片头、静音或片尾可作为无实质内容的区间记录。时间连续检查仅用于发现遗漏，不能证明句子已正确识别。需要核对但暂未核对的项目用 `verified: false`，缺口写入 `unresolved_gaps`，此时不能清理媒体。

用 `attachments` 列出证据用到的所有本地截图或其他持久文件；路径相对证据 JSON。Markdown 笔记里的本地图片也会独立检查。来源是本地用户文件时记录其绝对原路径，原文件仍不属于清理范围。

自动阈值只帮助定位 ASR 疑点，不能作为准确率估计。低置信片段和空语音块应核对是静音、识别失败还是缺失内容；有实质内容的章不能用“没有语音”跳过。
