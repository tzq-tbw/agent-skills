# 模式 C 扩展接口（暂不启用）

复习记录 schema_version=1，按小节保存 section_id、subject、chapter、section、questions。
每题保存稳定 id、fingerprint、knowledge_tags、error_type、mastery、review_count、last_review、next_review、history。
history 追加 event_id、date、level、prompt、answer、hints、evidence、simulated；重复 event_id 拒绝写入。

未来用户主动启用模式 C 时，按上述字段汇总学科、章节、小节、知识点、错误类型、掌握等级和历史趋势；直接读取现有记录，不重新识别原图或生成 PDF，不改复习计划。无完整做题总数时只能说错题分布，不能说错误率；缺历史时不能编造趋势。当前不运行统计，也不生成额外统计文件。
