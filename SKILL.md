---
name: url-to-ima
description: "将网页/文章 URL 整理为 Markdown 文档并存入用户指定的 ima 知识库。流程：抓取正文（含图片Base64内嵌、代码/提示词全文保留、存疑文字标记）→ 深度结构化整理成 md → create_media→COS上传→add_knowledge 入库 → 核验 → 确认成功后才清理本地临时文件。适用于把收藏的公众号/知乎/网页文章沉淀进 ima 知识库。"
description_zh: "网页URL整理为Markdown并存入指定ima知识库（图片Base64内嵌/代码全文/存疑文字标记）"
version: 2.0.0
author: "USER"
agent_created: true
allowed-tools: Read,Write,Edit,Bash,PowerShell,Glob,Grep,WebFetch,Skill,AskUserQuestion,DeferExecuteTool,ToolSearch
display_name: "url-to-ima"
visibility: "private"
---

# url-to-ima

把任意网页/文章 URL 抓下来，整理成结构清晰的 **Markdown（.md）**，再存入**用户指定的** ima 知识库。

> 本 skill 自身只做"流程编排与文档整理"。真正的入库动作依赖 `ima-mcp` 连接器的工具（`create_media` / `add_knowledge` / `get_knowledge_list` / `get_addable_knowledge_base_list`），图片下载与 Base64 内嵌由本 skill 附带的脚本完成。**工具清单以 ima-mcp 服务端实际下发的为准，参数不要凭记忆猜。**

> 输出为 Markdown（.md）。图片以 **Base64 data URI 内嵌**进 md（单文件自包含、零外链）；"存疑"内容用 **【存疑】…【/存疑】** 包裹标注。

## 三条硬规则（必须遵守）

1. **URL 缺失 → 必须先问。** 调用时若用户没给 URL，用 AskUserQuestion / 直接提问要求提供，禁止自行编造或跳过。
2. **目标知识库缺失 → 必须先问。** 绝不默认存到某个库或根目录。用户必须在调用时指定 ima 知识库（即"目录"）。若未指定：先调 `get_addable_knowledge_base_list` 列出当前账号**可写入**的知识库，再用 AskUserQuestion 让用户选择；用户报库名时按名匹配 `knowledge_base_id`。**能看见不等于能写入**，一定要用"可添加"列表。
3. **确认上传成功后，才删除本地临时文件。** 流程结束前必须核验（见 Step 5）。只有 `media_state=2`（解析成功）或确认已出现在目标库列表里，才清理本次生成的 md（及 `images/` 文件夹、`mapping.json`）。**未确认成功前绝不删除**，以便用户手动重试。

## 内容整理四准则（用户硬性要求，覆盖所有文章）

1. **深度总结，且原文内容与意思不变。**
   - 输出是"深度结构化整理/总结"：在文首加一段**内容概要**便于速览；正文按原文逻辑分节重组，对啰嗦表达/营销噪音做收敛。
   - **红线**：不得删减、不得改写失真、不得改变任何事实/数据/观点/结论的原意。原文讲清楚的，必须讲清楚；原文没讲的，不得自行脑补。
   - 例外：若用户明确说"我要逐字原文、不要重组"，则退化为忠实转录（仍保留概要块与来源块）。执行前若拿不准，按"想清楚再写"原则问清楚。

2. **数据、图片、表格原样保存，不用外部引用或链接。**
   - 表格：用 Markdown 原生表格（`| 列 | 列 |`）。
   - 图片：**下载后以 Base64 `data:` URI 内嵌**进 md（见 Step 2c），保证单个 .md 自包含、离线也能看图、无任何外链。
   - 数据：原文的数字、统计、对比等一律照录，不四舍五入、不概括。

3. **代码、AI 提示词、实例、案例全文保留，以备参考。**
   - 所有代码块、提示词（prompt）、示例输入/输出、实操案例，用 Markdown 围栏代码块（```）**逐字**保留，不做删节、不转述、不"简化"。
   - 多行提示词尤其容易在整理时丢失，必须逐字保留。

4. **存疑内容用【存疑】…【/存疑】包裹标注。**
   - 凡是抓取不全、来源矛盾、AI 推断不确定、或无法核实的内容，必须用 **【存疑】** 开头、**【/存疑】** 结尾，把整段不确定内容包裹起来。
   - 不得把不确定内容伪装成确定事实；宁可标【存疑】，不可静默带过。
   - 图片下载失败也视为存疑：写为 `【存疑】[图：<说明> 未获取到]【/存疑】`，绝不静默丢弃。
   - 注：Markdown 无原生底色，故用【存疑】…【/存疑】文字包裹标记。

## 环境准备（首次使用）
本 skill 的 3 个脚本需要 Python 3 与下列依赖。建议新建一个独立虚拟环境（位置任意）：

1. 创建虚拟环境：`python3 -m venv <venv>`
2. 安装依赖：`pip install beautifulsoup4 lxml cos-python-sdk-v5`（若用 uv：`uv pip install --python <venv> beautifulsoup4 lxml cos-python-sdk-v5`）
3. 下文中的 `<PY>` 均指该虚拟环境的 Python 解释器：Windows 为 `<venv>\Scripts\python.exe`，macOS/Linux 为 `<venv>/bin/python`。

## 完整流程

### Step 0 收集入参
- `url`：一个或多个文章 URL（缺失 → 规则 1，问）。
- `knowledge_base_id`：目标 ima 知识库（缺失 → 规则 2，问）。
- 可选 `folder_id`：若用户明确要存进某库内的某个**已存在**文件夹，先用 `get_knowledge_list`（knowledge_base_id + FOLDER 过滤）在该库内查到对应 `folder_id`；ima 连接器不支持新建文件夹，**不要臆造 folder_id**，没有就存库根目录。

### Step 1 抓取正文
对每篇 URL 用 `WebFetch` 提取：标题、作者/来源、发布时间、全部正文。**保留原文层级结构、章节小标题、要点列表、提示词/操作步骤、案例/代码**（准则 1、3）。WebFetch 若对图片给出了位置/说明（如"[图：xxx]"或 alt 文本），一并记下，供 Step 2 放图用（按文档顺序与 Step 1b 下载的图片一一对应）。知乎/公众号若反爬失败，再用浏览器技能兜底。

### Step 1b 图片下载（准则 2 落地，必做）
直接用本 skill 附带的 `scripts/fetch_images.py`：对原 URL 做原始抓取，解析所有 `<img>`（兼容 `data-src`/`data-original` 懒加载、相对路径补全），逐张下载到本次临时目录的 `images/` 子文件夹，按文档顺序命名为 `img_01.png`/`img_02.jpg`…，并输出 `mapping.json`（原图 src → 本地文件名；下载失败记为 `null`），同时给出 `ordered` 有序列表（src / file / alt 占位 / ok）。

```bash
<PY> url-to-ima/scripts/fetch_images.py <文章URL> <临时目录>/images <临时目录>/mapping.json
```
> 微信/知乎等站点图片可能带时效签名或防盗链，抓取失败率较高——以 `mapping.json` 的 `null`/`ok=false` 为准如实标注，不要假装成功。

### Step 2 整理为 Markdown（结构化文章）
写一个干净的 `.md`（UTF-8），结构如下：
1. **标题**（一级 `#`）。
2. **来源信息行**：作者/公众号、发布时间、原始链接。
3. **内容概要**（准则 1）：2–5 句话概括全文主旨与要点，不得引入原文没有的结论。
4. **正文**：按原文逻辑分节（`##`/`###` + 段落/列表）。要求：
   - 数据、表格用 Markdown 表格原样保留；
   - 图片先按文档顺序写成本地相对引用 `![<说明>](images/img_0N.<ext>)`（N 与 Step 1b 下载顺序对应；无法对应的图直接写 `【存疑】[图：<说明> 未获取到]【/存疑】`）；
   - 代码、提示词、实例、案例用 ``` 围栏代码块**逐字**保留（准则 3）；
   - 存疑内容用 **【存疑】…【/存疑】** 包裹（准则 4）。
5. **来源块**（文末）：原始链接、说明"本文为对原网页的忠实深度整理，已去除营销/视频占位噪音，图片已 Base64 内嵌"。

**不要**往 md 里写任何"需求依据编号"之类标注。

#### Step 2c 图片 Base64 内嵌（把本地引用替换为 data URI）
直接用 `scripts/embed_base64.py`：扫描 md 里的 `![alt](images/xxx)` 本地图片引用，读取对应文件并替换为 `![alt](data:image/<ext>;base64,<内容>)`；找不到的文件（下载失败）替换为 `【存疑】[图：alt 未获取到]【/存疑】`。

```bash
<PY> url-to-ima/scripts/embed_base64.py <临时目录>/xxx.md
```
执行后 md 即为**完全自包含、零外链**的单文件。

- 保存路径：在当前工作区新建一个**专用临时子目录**（如 `url-to-ima-tmp/`）放本次生成物，其下再建 `images/` 存图，便于 Step 6 安全清理。文件名用中文标题，如 `设计门槛没了_Lovart与3个设计Skill.md`。

### Step 3（归档为 .md，无需转换）
Markdown 是纯文本，无需格式转换。Step 2c 完成后即可直接入库。记录 md 的真实字节数 `file_size` 供 Step 4 用。

### Step 4 入库三连（必须紧挨着执行，避免 STS 过期）
> **入库三连缺一不可**：本地文件入库是"create_media → 用凭证上传 COS → add_knowledge"三步，缺任何一步都不算入库。尤其最后一步 `add_knowledge` 必调，否则文件不会出现在知识库里。

**4a. create_media（取新鲜 STS 凭证 + media_id）**
参数：`knowledge_base_id`、`file_name`（用文章标题.md）、`file_size`（必须与 Step 3 实际字节数一致）、`content_type`（md 用 `text/markdown`）、`file_ext`（md）。
返回体里取：`media_id`（顶层）和 `cos_credential`（含 `secret_id/secret_key/token/region/bucket_name/cos_key/file_ext`）。**把 `cos_credential` 整个对象写到一个 JSON 文件**（如 `cred.json`）。

`content_type` 对照（按扩展名精确填）：
| 扩展名 | content_type |
|---|---|
| md | text/markdown |
| docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| pdf | application/pdf |
| doc | application/msword |
| txt | text/plain |

**4b. 上传到 COS（用官方 SDK，禁止手写签名）**
直接用本 skill 附带的 `scripts/upload_cos.py`：
```bash
<PY> url-to-ima/scripts/upload_cos.py <cred.json 路径> <本地 md 路径>
```
脚本内部用 `cos-python-sdk-v5` 的 `CosConfig(...)` + `CosS3Client.put_object(...)` 上传。**不要**手写 COS 签名——手写签名会稳定得到 403。
> 若虚拟环境里缺少依赖，按"环境准备"一节安装（`beautifulsoup4 lxml cos-python-sdk-v5`）。
> STS 凭证是短时效，但**务必在拿到凭证后立刻上传**，不要在中间做耗时操作，否则易遇 `InvalidAccessKeyId`。

**4c. add_knowledge（入库，必调！）**
参数：`knowledge_base_id`、`media_id`（来自 4a）。可选 `folder_id`（Step 0 拿到的话）、`duplicate_name_strategy`（默认 SAVE 保留）。这一步才是把文件真正提交进知识库。

### Step 5 核验
调 `get_knowledge_list`（knowledge_base_id，过滤掉 FOLDER）查目标库，确认：
- 列表里出现了本次的 `media_id` / 文件名；
- 其 `media_state=2`（MEDIA_PARSE_SUCCESS）即解析成功。
入库是异步的，刚导入可能还在 `MEDIA_PARSING`（state=1）。若显示解析中，如实告知用户"稍后可在 ima 查到"，不要当成失败。只有确认 `media_state=2` 或已稳定出现在列表，**才算上传成功**。

### Step 6 清理（仅成功时）
仅当 Step 5 确认成功后：删除本次在临时目录生成的全部产物——`*.md`、`mapping.json`、以及 `images/` 子文件夹（含下载的原图）。
- 推荐做法：本次所有生成物都放在专用临时子目录（Step 2 建的），成功后直接删除该子目录即可，干净且不会误删用户既有文件。
- **未确认成功 → 不删**，保留临时目录（含已下载图片）供用户手动重试或排查。

## 常见问题与处置
| 现象 | 原因 | 处置 |
|---|---|---|
| 上传返回 403 `InvalidAccessKeyId` | create_media 与上传间隔太久，STS 凭证过期 | 拿到凭证后立刻上传；不要提前很久调 create_media |
| 上传 403 `SignatureDoesNotMatch` | 手写 COS 签名算法有 bug | 改用官方 `cos-python-sdk-v5`，不要手写 |
| 文件上传了却不在 ima 里 | **漏调 `add_knowledge`** | 三步缺一不可，最后必须调入库接口 |
| md 里图片显示成破图/外链 | 没跑 `embed_base64.py`，仍是用本地 `images/` 相对路径 | Step 2c 必须执行，把图片 Base64 内嵌进 md |
| 图片下载失败被忽略 | fetch_images 报 null 但整理时没标存疑 | 下载失败处写 `【存疑】[图：... 未获取到]【/存疑】` |

## 附：本 skill 提供的文件
- `scripts/fetch_images.py`：对文章 URL 原始抓取，下载全部图片到 `images/`，输出 `mapping.json`（原图 src → 本地文件名 / 失败为 null，含 ordered 有序列表）（Step 1b 用）。
- `scripts/embed_base64.py`：把 md 里的本地图片引用 `![alt](images/xxx)` 替换为 Base64 `data:` URI；找不到的文件（下载失败）替换为 `【存疑】[图：alt 未获取到]【/存疑】`（Step 2c 用）。
- `scripts/upload_cos.py`：读取 `cos_credential` JSON + 本地文件，用官方 SDK 上传到 COS（Step 4b 用）。
