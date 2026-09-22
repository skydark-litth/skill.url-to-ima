"""Step 2 组装：把 extract_article.py 的中间稿转成 Markdown 正文（图片先写本地相对引用）。

用法：
    <PY> build_md.py <article_raw.txt> <mapping.json> <body.md 输出>

产物只含 `# 标题` + 正文（[CODE]/[TABLE]/[[IMG]] 全部转换完成）。
文首的「来源信息行 + 内容概要」与文末「来源块」需由 agent 自行补写（属判断性内容，不脚本化）。
之后继续跑 normalize_images.py（统一 WebP，内部会同步引用后缀）→ embed_base64.py。
"""
import sys, re, json

RAW, MAP, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

mapping = json.load(open(MAP, encoding='utf-8'))
src2file = {it['src']: it['file'] for it in mapping.get('ordered', []) if it.get('ok') and it.get('file')}

text = open(RAW, encoding='utf-8').read()
meta_str, body = text.split('=== BODY ===', 1)
meta = json.loads(meta_str.replace('=== META ===', '').strip())
body = body.strip()

img_order = []

def fix_table(block: str) -> str:
    """Markdown 表格必须有分隔行（|---|---|）才能渲染；extract 输出只有数据行，此处按首行列数补插。"""
    lines = [l for l in block.split('\n') if l.strip()]
    if not lines:
        return block
    cols = lines[0].strip().strip('|').count('|') + 1
    sep = '| ' + ' | '.join(['---'] * cols) + ' |'
    if len(lines) >= 2 and set(lines[1].replace('|', '').replace('-', '').strip()) == set():
        return '\n'.join(lines)  # 已有分隔行
    return lines[0] + '\n' + sep + '\n' + '\n'.join(lines[1:])

def img_repl(m):
    src = m.group(1)
    f = src2file.get(src)
    if not f:
        return '【存疑】[图：原文配图 未获取到]【/存疑】'
    if src not in img_order:
        img_order.append(src)
    return f'[[LOCALIMG:{f}]]'

body = re.sub(r'\[\[IMG:([^\]]+)\]\]', img_repl, body)

def code_repl(m):
    """把 [CODE:lang]…[/CODE] 转成围栏代码块；内容中的反引号用更长围栏规避破块。"""
    lang = (m.group(1) or '').strip()
    inner = m.group(2).strip('\n')
    runs = [len(x) for x in re.findall(r'`+', inner)]
    fence = '`' * max(3, (max(runs) + 1) if runs else 0)
    return f'{fence}{lang or "text"}\n{inner}\n{fence}'

body = re.sub(r'\[CODE(?::([^\]]*))?\](.*?)\[/CODE\]', code_repl, body, flags=re.S)
body = re.sub(r'\[TABLE\](.*?)\[/TABLE\]',
              lambda m: fix_table(m.group(1).strip()), body, flags=re.S)

idx = {src: i + 1 for i, src in enumerate(img_order)}
file2n = {src2file[s]: n for s, n in idx.items()}

def local_repl(m):
    v = m.group(1)
    n = file2n.get(v, 0)
    if v.startswith('data:'):
        return f'![原文配图 {n:02d}]({v})'          # 内联图片：直接原样输出 data URI
    return f'![原文配图 {n:02d}](images/{v})'

body = re.sub(r'\[\[LOCALIMG:([^\]]+)\]\]', local_repl, body)

md = f"# {meta['title']}\n\n" + body + '\n'
open(OUT, 'w', encoding='utf-8').write(md)

print('title:', meta['title'])
print('images mapped:', len(img_order), '/', len(re.findall(r'!\[原文配图', md)))
print('unresolved img:', md.count('未获取到'))
print('code fences:', len(re.findall(r'^`{3,}', md, flags=re.M)) // 2)
print('downloaded-but-unused imgs:', len([s for s in src2file if s not in img_order]))
print('bytes:', len(md.encode('utf-8')))
