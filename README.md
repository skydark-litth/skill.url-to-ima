# skill-url-to-ima

将任意网页 / 文章 URL 抓取下來，整理为**自包含的 Markdown（.md）**，再存入**用户指定的** ima 知识库（腾讯 ima 的"资料库"）。

本技能解决的核心痛点：收藏的文章想沉淀进 ima 知识库时，往往要手动复制、丢图、丢代码、丢提示词。它把"抓取 → 深度整理 → 入库"串成一条可复用的流程，并保证：

- **图片原样保存**：下载后以 Base64 `data:` URI 直接内嵌进 md，单文件自包含、离线也能看图、零外链。
- **代码 / 提示词 / 案例全文保留**：用 Markdown 围栏代码块逐字保留，不删节、不转述。
- **存疑内容显式标记**：抓取不全或无法核实的内容用 `【存疑】…【/存疑】` 包裹，绝不把不确定信息伪装成事实。
- **深度整理但不失真**：在文首加内容概要，正文按原文逻辑重组、收敛营销噪音；原文的事实 / 数据 / 观点原意不变。

## 目录结构

```
skill-url-to-ima/
├── SKILL.md              # 技能主文档：流程、硬规则、内容四准则、踩坑与处置
├── README.md             # 本说明文件
└── scripts/
    ├── fetch_images.py   # 对文章 URL 原始抓取，下载全部图片到 images/，输出 mapping.json
    ├── embed_base64.py   # 将 md 中的本地图片引用替换为 Base64 data: URI（或标存疑）
    └── upload_cos.py     # 用官方 cos-python-sdk-v5 将文件上传到 ima 的 COS 存储
```

## 使用前提

1. **WorkBuddy 环境**：本技能作为 WorkBuddy 的 Skill 使用，由 WorkBuddy 的 Agent 在对话中调用。
2. **ima-mcp 连接器**：需在 WorkBuddy 中连接 `ima` 连接器（提供 `create_media` / `add_knowledge` / `get_knowledge_list` / `get_addable_knowledge_base_list` 等工具），真实的"存入知识库"动作由这些工具完成。
3. **Python 依赖**：技能附带的 3 个脚本需要 Python 3 与以下依赖：
   ```bash
   python3 -m venv .venv
   pip install beautifulsoup4 lxml cos-python-sdk-v5
   ```
   脚本调用时统一用该虚拟环境的解释器（Windows：`.venv\Scripts\python.exe`，macOS/Linux：`.venv/bin/python`）。

## 工作流程（摘要）

| 步骤 | 动作 |
|------|------|
| 0 | 收集入参：文章 URL（必填）、目标 ima 知识库（必填，未指定则询问）；二者缺失都不擅自进行 |
| 1 | 抓取正文（保留层级、提示词、代码、案例）；同时下载图片到 `images/` 并生成 `mapping.json` |
| 2 | 整理为 Markdown：标题 → 来源信息 → 内容概要 → 正文（表格 / 图片引用 / 代码块 / 存疑包裹）→ 来源块；再跑 `embed_base64.py` 把图片内嵌为 Base64 |
| 3 | 入库三连（必须紧挨着执行，避免 STS 凭证过期）：`create_media` 取凭证 → `upload_cos.py` 上传 COS → `add_knowledge` 入库 |
| 4 | 核验：确认文件出现在目标知识库且 `media_state=2`（解析成功） |
| 5 | 仅当核验成功后，才清理本次生成的本地临时文件 |

> 完整规则与"常见问题处置"见 [SKILL.md](./SKILL.md)。

## 说明

- 本技能**只做流程编排与文档整理**，不内置任何 ima 账号凭据；入库动作完全依赖用户已连接的 ima-mcp 连接器。
- 三条硬规则（缺 URL 先问、缺目标库先问、确认成功才删本地文件）在任何调用下都优先遵守。
