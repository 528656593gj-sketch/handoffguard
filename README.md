# HandoffGuard｜交付包体检器

一个离线运行的交付前检查工具，同时提供可安装的 Agent Skill。它扫描文件夹或 ZIP，对照交付清单寻找缺失文件、空文件、重复内容、多个疑似最终版本和临时文件，并生成可分享的 Markdown 报告。

## 为什么做

很多返工不是内容能力不足，而是交付时漏了附件、放错版本、带上空文件，或者没人能确认哪个才是最终版。HandoffGuard 把这类可确定检查交给程序完成。

## 当前能力

- 文件夹和 ZIP 扫描
- 必交文件数量、扩展名和文件名模式检查
- 空文件检查
- 基于 SHA-256 的重复内容检查
- 多个疑似最终版本检查
- 临时文件和系统文件提醒
- 文件扩展名与真实内容不一致提醒
- Markdown 和可选 JSON 报告
- 无第三方 Python 依赖、无需 API Key
- 经用户确认后创建安全修复副本，不覆盖原始 ZIP

它只验证交付包结构，不判断视频、设计或文档的创意质量。

## 真实测试结果

一次匿名化的视频交付测试中，初始 ZIP 包含重复成片、重复封面、Mac 隐藏文件、双重扩展名，以及被 Word 自动保存成 `.docx` 的字幕文件。

| 阶段 | 文件数 | 错误 | 警告 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 初次检查 | 9 | 1 | 7 | BLOCKED |
| 创建修复副本后 | 6 | 0 | 0 | PASS |

HandoffGuard 保留原始包，并在新 ZIP 中完成可确定的机械修复；缺少的创作素材不会被伪造。完整案例见 [docs/demo-case.md](docs/demo-case.md)。

## 快速开始

需要 Python 3.10 或更高版本。

```bash
python3 scripts/handoffguard.py ./delivery \
  --rules examples/checklist.json \
  --output handoffguard-report.md
```

也可以直接检查 ZIP：

```bash
python3 scripts/handoffguard.py ./delivery.zip --output report.md
```

需要修复可确定的问题时，生成一个新的 ZIP：

```bash
python3 scripts/repair_package.py ./delivery.zip \
  --output repaired-delivery.zip \
  --log repair-log.md
```

修复功能不会伪造缺少的字幕、封面或其他创作内容。

不提供清单时，仍会检查空文件、重复文件、版本混乱和临时文件，但不会猜测哪些文件必须存在。

## 清单示例

```json
{
  "project_name": "30秒视频交付",
  "required": [
    {
      "label": "字幕",
      "extensions": [".srt"],
      "min_count": 1,
      "max_count": 1
    }
  ]
}
```

完整字段说明见 [references/checklist-schema.md](references/checklist-schema.md)。

## 作为 Skill 使用

将仓库放入 Codex 可发现的 Skill 目录，然后调用：

```text
Use $handoffguard to audit this delivery folder against its checklist.
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 路线图

- v0.1：确定性离线检查
- v0.2：可选 AI，将自然语言交付要求转换为 JSON 清单
- v0.3：更多内容级检查器，例如视频编码参数、图片尺寸和文档页数

## 隐私

默认模式完全在本地读取文件元数据与内容哈希，不上传文件。请勿将没有权利分享的工作资料发送到外部服务。

## License

MIT
