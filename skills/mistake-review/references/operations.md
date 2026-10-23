# 工具调用

使用当前环境可用的 Python 3，建议 Python 3.10+，检查实际解释器和 `pypdf` 是否可用，不沿用其他机器的解释器路径。

公开包不附编译器二进制。可使用 PATH 中的 Tectonic，或通过 `--compiler` 指定 Tectonic / XeLaTeX 的实际路径。Tectonic 首次编译可能联网下载 TeX 宏包；官方发行包见 https://github.com/tectonic-typesetting/tectonic/releases 。脚本也兼容用户自行放入 `tools/tectonic.exe` 的本机配置，但不将其视为必然存在。

```text
python scripts/workflow.py prepare batch.json --library <用户指定的错题库> --stage <库外草稿目录>
python scripts/workflow.py archive <草稿目录> --confirmed --compiler <tectonic.exe或xelatex.exe>
python scripts/workflow.py due --library <用户指定的错题库> --date <YYYY-MM-DD>
python scripts/workflow.py review <小节目录> --question <ID> --date <YYYY-MM-DD> --level L2 --prompt <提问> --answer <回答摘要> --hints 1 --evidence <评价依据> --event <本次唯一ID>
```

`--test-only` 是 prepare 的隔离测试选项：library 路径必须包含“测试验证”，且 archive 不要求人类审校，但所有生成正文和复习记录会标记为测试。不要用它绕过正式归档确认。

prepare 输入示例（UTF-8 JSON；公式使用 `$...$` 或 `$$...$$`，字符串中反斜杠须按 JSON 转义）：

```json
{
  "subject": "高等数学", "chapter": "二重积分", "section": "计算二重积分",
  "summary": "本小节知识与方法总结。",
  "questions": [{
    "statement": "完整题目，含所有条件。",
    "knowledge": "主要知识点。", "approach": "选择方法的理由。",
    "solution": "经验证的详细解答。",
    "errors": "实际错因：待确认。常见易错点：……",
    "method": "可迁移方法。", "tags": ["对称性"], "error_type": "待确认",
    "sources": [{"path": "<原材料绝对路径>", "location": "例14"}]
  }]
}
```

目录名不允许路径分隔符、`..` 或 Windows 保留名。重复题按规范化原文指纹阻止自动追加；工具不判断改写后的语义重复，由代理检查。修改已确认旧题须另行取得明确授权并局部编辑，此脚本只提供增量追加，不支持隐式覆盖旧题。

工具生成 `receipt.json` 和 Markdown 预览；归档前只能修改批次 JSON 后重新 prepare，不能手改 receipt。archive 会检查预览和原库哈希，防止提交被改过或过期的草稿。归档在小节 `.backups/<批次>/` 保存旧文件；遇可捕获写入错误回滚。硬件故障/进程强杀后的多文件提交不保证原子性，应从 backup 恢复后核对，不能直接宣称已完成。PDF 编译日志保留在草稿目录。

PDF 模板使用 ctex、amsmath、fontspec，A4 纵向。题目区只显示题面和重做空白，解析区显示知识点、思路、解答、错因、总结；Markdown 保留 Obsidian 公式和稳定题号。TeX 与 PDF 同时归档。编译后必须用 pdftoppm 渲染并看图，成功退出码不等于版式通过。

有图时，在对应题 JSON 增加 `"diagram": {"path": "<已检查的图形PNG绝对路径>", "caption": "图注"}`。若同目录有同名 PDF，工具会一并复制到小节 `assets/`；Markdown 使用 PNG，LaTeX 优先使用矢量 PDF。先由代理按题设用 TikZ 等工具重画并检查，不由归档脚本猜测函数或区域。图形不参与题目 ID 计算，增加或改图不改变原题 ID。已有题目仅补图时，须保持题面和复习 JSON 不变，并刷新待确认草稿的附件及正文哈希。
