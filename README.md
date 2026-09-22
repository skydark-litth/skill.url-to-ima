# url-to-ima

把任意网页 / 文章 URL 抓下来，经 **AI 大模型分析蒸馏**，整理成分门别类、逻辑清晰、顺畅可读的 **Markdown 知识库文章（.md）**，再存入**用户指定的** ima 知识库。

> 本 skill 只做「流程编排与文档蒸馏整理」。真正的入库动作依赖 `ima-mcp` 连接器的工具（`create_media` / `add_knowledge` / `get_knowledge_list` / `get_addable_knowledge_base_list`），图片下载与 Base64 内嵌由本 skill 附带的脚本完成。**工具清单以 ima-mcp 服务端实际下发的为准，参数不要凭记忆猜。**

> 输出为 Markdown（.md）。叙述 / 对话性文字经 AI 蒸馏为知识讲解（去除聊天式对话、寒暄、营销噪音）；**代码、命令、提示词逐字保留**，数据 / 表格原样保留；图片以 **Base64 data URI 内嵌**进 md（单文件自包含、零外链）；「存疑」内容用 **【存疑】…【/存疑】** 包裹标注。

## 适用场景

- 把收藏的微信公众号文章、知乎文章、各类普通网页，沉淀进 ima 知识库；
- 形成**可检索、离线可读、结构化**的个人 / 团队知识档案；
- 自动去除广告图、聊天式对话、寒暄与营销噪音，只保留知识讲解、功能说明、示例、经验心得与图表。

## 核心特性

- **AI 蒸馏为知识库文章**：读到全部文字后由大模型分析总结，保留知识相关内容，剔除聊天式对话与寒暄，**按知识主题分门别类、逻辑清晰地重组**为顺畅可读的连贯文章（不做原子化卡片 / 重流程，以可读性为先）。
- **多源适配**：内置正文容器识别，覆盖公众号（`#js_content`）、知乎（`.RichText` / `#js_article`）、`.markdown-body`、`.post-content`、`.article-content`、`article`、`main` 等，并带「文本量最大的紧凑容器」启发式兜底。
- **广告过滤靠人眼**：广告图及其配套推广文字由大模型（agent）逐张看图判定，**禁止脚本按关键词自动删**（避免把正文教程截图误删）。
- **图片规格统一**：进入成品的图片统一转 **WebP（quality=98、支持透明）**，最长边超 1600px 等比缩小；动图保留动画。
- **自包含 Markdown**：图片全部 Base64 内嵌，单文件离线可读、零外链。
- **知识保真**：蒸馏不改原意、不丢知识点；数据、表格原样照录；**代码 / 命令 / 提示词逐字保留**（蒸馏例外）；抓不全或不确定处用【存疑】标注。
- **入库三连**：`create_media`（取 STS 凭证）→ COS 上传（官方 SDK）→ `add_knowledge`，缺一步都不算入库。
- **安全清理**：只有确认 `media_state=2`（解析成功）或已稳定出现在知识库，才删除本地临时文件。

## 三条硬规则

1. **URL 缺失 → 必须先问。** 没给 URL 不得自行编造或跳过。
2. **目标知识库缺失 → 必须先问。** 绝不默认存到某库或根目录；用 `get_addable_knowledge_base_list` 列出**可写入**的库让用户选（能看见 ≠ 能写入）。
3. **确认上传成功后，才删除本地临时文件。** 未确认成功前绝不删除，便于手动重试。

## 内容整理四准则

1. **AI 蒸馏为知识库文章，且原文知识与意思不变。** 保留知识讲解 / 功能说明 / 示例 / 经验心得，剔除聊天对话 / 寒暄 / 营销噪音，按知识主题分门别类重组，行文顺畅可读；不丢知识点、不改原意、不脑补。
2. **数据、图片、表格原样保存，不用外部引用或链接。** 表格用原生 `| 列 | 列 |`；图片 Base64 内嵌；数字照录不四舍五入。
3. **代码、命令、AI 提示词全文保留。** 作为蒸馏例外，用围栏代码块逐字保留，可直接照做。
4. **存疑内容用【存疑】…【/存疑】包裹。** 抓不全 / 来源矛盾 / 推断不确定 / 无法核实，一律标【存疑】，不得伪装成确定事实。

## 工作流概览

| 阶段 | 步骤 | 工具 / 脚本 |
|---|---|---|
| 收集入参 | Step 0 | `url`、`knowledge_base_id`（缺失则问） |
| 抓取正文 | Step 1 | `scripts/extract_article.py` → 中间稿（正文块 + 图片占位） |
| 下载图片 | Step 1b | `scripts/fetch_images.py` → `images/` + `mapping.json` |
| 广告过滤 | Step 1c | 大模型逐图目视判定 → `--drop` 重跑排除 |
| 机械全文草稿 | Step 2a | `scripts/build_md.py` → `draft.md`（待蒸馏原料） |
| AI 蒸馏重组 | Step 2b | 大模型按知识主题蒸馏 → `body.md` |
| 图片规格统一 + 内嵌 | Step 2c | `normalize_images.py`（转 WebP / 限 1600px）→ `embed_base64.py`（自包含 md） |
| 入库三连 | Step 4 | `create_media` → `scripts/upload_cos.py` → `add_knowledge` |
| 核验 | Step 5 | `get_knowledge_list` 确认 `media_state=2` |
| 清理 | Step 6 | 仅成功时删除临时目录 |

> 完整细节（含参数、异常处理、FAQ 排错表）见仓库内 [`SKILL.md`](./SKILL.md)。

## 脚本清单

| 脚本 | 作用 |
|---|---|
| `scripts/article_common.py` | 共用工具层：HTML 缓存、正文容器识别、懒加载取值、统一图片序列 |
| `scripts/extract_article.py` | 解析正文，输出「正文块 + 图片占位」有序中间稿；上报装饰图与广告候选 |
| `scripts/fetch_images.py` | 在正文容器内按统一序列下载图片，输出 `mapping.json` |
| `scripts/build_md.py` | 中间稿 + `mapping.json` 组装**机械全文草稿**（待 AI 蒸馏） |
| `scripts/normalize_images.py` | 图片统一转 WebP、限 1600px，并同步 md 引用 |
| `scripts/embed_base64.py` | 本地图片引用替换为 Base64 `data:` URI |
| `scripts/upload_cos.py` | 读取 `cos_credential` JSON + 文件，用官方 SDK 上传 COS |

## 环境准备

本 skill 的脚本需要 **Python 3** 与以下依赖。虚拟环境建在**技能目录之外**（技能目录要能被复制 / 分发 / 提交）：

```bash
# 1. 创建虚拟环境（Windows 建议 %USERPROFILE%\.venv-url-to-ima）
python3 -m venv <venv>

# 2. 安装依赖（一律官方源）
<PY> -m pip install -i https://pypi.org/simple beautifulsoup4 lxml cos-python-sdk-v5 pillow
```

- `<PY>`：Windows 为 `<venv>\Scripts\python.exe`，macOS/Linux 为 `<venv>/bin/python`。
- **依赖安装源硬规则**：默认只用官方源，禁用镜像源；官方源不可用时需先征得用户同意再切换。

## 安全与数据说明

- 入库动作通过你自己的 ima 账号完成，文件落在你指定的知识库；**不会**上传到任何第三方平台。
- 私钥、token 等凭据不参与任何仓库同步。
- 广告判定由本地大模型执行，图片不离开本机即被用于判定。

## 版本

- 当前版本：**v2.7.0**（详见 [`SKILL.md`](./SKILL.md) 顶部 `version` 字段）。
