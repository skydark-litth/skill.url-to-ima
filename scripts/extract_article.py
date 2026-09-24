"""Step 1：解析文章正文，输出「正文块 + 图片占位」有序中间稿。

用法：
    <PY> extract_article.py <文章URL> <输出 txt 路径> [--drop 1,10]

适配范围：微信公众号（#js_content）以及其他常见文章页（article / main / 常见正文容器）。
正文根定位、懒加载取值、图片编号均与 fetch_images.py 共用 article_common.py，
因此 agent 按文件名 img_0N 看图得到的「第 N 张」可直接写进 `--drop N`。

广告/噪音图过滤策略（两段式，避免误删正文配图）：
- 自动丢弃：装饰性占位图/统计像素（声明宽度 <= 100px），无内容价值，记入 META.images_auto_dropped。
- 候选上报：文章首图（正文开始前）、文末图（正文结束后）、以及紧邻短促引导句（点击/扫码/关注…）的图片，
  写入 META.ad_candidates 供 agent **用 Read 直接看图**判定；确认是广告/二维码/引流图的，用 `--drop`
  按正文图片序号排除。**不要仅凭关键词自动删图**——教程类文章正文里常出现「点击+号」等字样，会误删正文配图。
"""
import sys, re, json, os, datetime
from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from article_common import (load_or_fetch_html, find_content_root, img_width,
                            img_index_map, page_meta)

URL = sys.argv[1]
OUT = sys.argv[2]
DROP = set()
if '--drop' in sys.argv:
    raw = sys.argv[sys.argv.index('--drop') + 1]
    DROP = {int(x) for x in re.split(r'[,\s]+', raw.strip()) if x.strip().isdigit()}

WORKDIR = os.path.dirname(os.path.abspath(OUT))
html, cache_file = load_or_fetch_html(URL, WORKDIR)

soup = BeautifulSoup(html, 'lxml')
content, root_sel = find_content_root(soup)

def grab(pat):
    m = re.findall(pat, html)
    return m[0] if m else ''

# 元信息：公众号走 JS 变量；其他站点走通用 meta/标题兜底
gm = page_meta(soup)
meta = {
    'nickname': grab(r'var nickname = "([^"]*)"') or grab(r"var nickname = '([^']*)'"),
    'ct': grab(r'var ct = "(\d+)"'),
    'title': (grab(r'var msg_title = [\'"]([^\'"]*)') or gm['title'] or ''),
    'author': (grab(r'var author = [\'"]([^\'"]*)') or gm['author']),
    'publish_generic': gm['publish'],
    'content_root': root_sel,
    'source_url': URL,
}
if meta['ct']:
    ts = int(meta['ct'])
    meta['publish_bj'] = datetime.datetime.fromtimestamp(
        ts + 8 * 3600, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
else:
    meta['publish_bj'] = meta['publish_generic']

meta['images_in_content'] = len(content.find_all('img'))
meta['images_all'] = len(soup.find_all('img'))

BLOCK = {'p', 'div', 'section', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'ul', 'ol',
         'blockquote', 'pre', 'figure', 'figcaption', 'table', 'tr', 'td', 'th', 'img'}
# 引导语关键词仅用于**生成候选线索**，不参与自动删除（判定必须由 agent 看图）
CTA = re.compile(r'(点击|戳|扫码|扫一扫|长按|识别图中|扫描二维码|关注|星标|订阅|加群|进群|入群|领取|'
                 r'报名|购买|下单|优惠|福利|课程|训练营|阅读原文|直达|入口|后台回复|'
                 r'subscribe|follow us|scan the qr|click here|buy now|sign up)', re.I)

# ---- 图片分类：装饰图自动丢弃 + 广告候选上报（候选需 agent 看图确认）----
IMG_IDX, IMG_SEQ = img_index_map(content)
in_imgs = [t for _, t, _ in IMG_SEQ]

def text_len_before_after():
    before, after = {}, {}
    cum = 0
    for d in content.descendants:
        if isinstance(d, Tag) and d.name == 'img':
            before[id(d)] = cum
        elif isinstance(d, NavigableString):
            cum += len(re.sub(r'\s+', '', str(d)))
    total = cum
    for im in in_imgs:
        after[id(im)] = total - before.get(id(im), 0)
    return before, after

TB, TA = text_len_before_after()

def prev_leaf_block(im):
    node = im
    for _ in range(6):
        node = node.find_previous(['p', 'section', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'li'])
        if node is None:
            return None
        if node.find('img') is not None:
            continue
        t = re.sub(r'\s+', '', node.get_text())
        if t:
            return t
    return None

auto_dropped, candidates = [], []
for im in in_imgs:
    n = IMG_IDX[id(im)]
    w = img_width(im)
    reasons = []
    if 0 < w <= 100:
        auto_dropped.append({'index': n, 'w': w, 'reason': '装饰占位图/统计像素（宽度<=100px）'})
        continue
    if n in DROP:
        auto_dropped.append({'index': n, 'w': w, 'reason': '人工指定排除（--drop）'})
        continue
    if TB.get(id(im), 9999) <= 120:
        reasons.append('位于正文开始前（可能是顶部横幅/关注引导）')
    if TA.get(id(im), 9999) <= 120:
        reasons.append('位于正文结束后（可能是文末引流图/二维码）')
    pb = prev_leaf_block(im)
    if pb and len(pb) <= 60 and CTA.search(pb):
        reasons.append(f'紧邻短促引导句：「{pb}」')
    if reasons:
        candidates.append({'index': n, 'w': w, 'ratio': im.get('data-ratio'),
                           'reasons': reasons, 'prev_text': (pb or '')[:60]})

meta['images_auto_dropped'] = auto_dropped
meta['ad_candidates'] = candidates
meta['drop_arg'] = sorted(DROP)

# 疑似「代码容器但不在 <pre> 内」：本脚本只逐字保留 <pre> 内容。若代码放在 div.code 之类
# 的非 pre 容器里，bs4 在解析阶段就会丢掉行首缩进（已实测），此处显式上报，
# 提醒 agent 对照原文核对/标注存疑，避免静默篡改代码。
CODEISH = re.compile(r'\b(highlight|hljs|prism|codehilite|code-block|codeblock|'
                     r'sourcecode|prettyprint|language-)\b', re.I)
suspect_code, seen_sig = [], set()
for el in content.find_all(['div', 'section']):
    cls = ' '.join(el.get('class') or [])
    if not cls or not CODEISH.search(cls):
        continue
    if el.find('pre') is not None or el.find('img') is not None:
        continue  # 内含 <pre> 的会正常走代码分支；含图的多半是版式容器
    t = el.get_text(' ', strip=True)
    if len(t) < 10:
        continue
    sig = (cls, t[:60])
    if sig in seen_sig:
        continue
    seen_sig.add(sig)
    suspect_code.append({'tag': el.name, 'class': cls, 'preview': t[:80]})
meta['code_without_pre'] = suspect_code

def norm(s):
    s = s.replace('\u200b', '').replace('\xa0', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()

def code_text(node):
    """verbatim text, <br> -> newline (do NOT use get_text here)"""
    parts = []
    for ch in node.children:
        if isinstance(ch, NavigableString):
            parts.append(str(ch))
        elif isinstance(ch, Tag):
            if ch.name == 'br':
                parts.append('\n')
            elif ch.name == 'code':
                # 微信 code-snippet__js 结构：pre 内每个 <code> 元素是一行，
                # 行间无 <br>/换行符，直接递归会把所有行粘连成一行——补 \n 分行。
                # 常规站点（GitHub/Prism 等）pre>code 只有一个包裹元素，
                # 多出的尾部 \n 会被下方空行清理逻辑去掉，无副作用。
                parts.append(code_text(ch) + '\n')
            else:
                parts.append(code_text(ch))
    return ''.join(parts)

def code_lang(node):
    """从 class 里探测代码语言（language-xxx / lang-xxx / highlight-source-xxx）。"""
    cands = [node] + node.find_all(['code', 'div'], limit=3)
    for el in cands:
        cls = ' '.join(el.get('class') or [])
        m = re.search(r'(?:language|lang|highlight-source|brush)[-:]([\w+#]+)', cls, re.I)
        if m:
            return m.group(1).lower()
    return ''

# 代码块只认 <pre>。**不要**把 div.highlight/code-block 之类也当代码容器：
# bs4 的 preserve_whitespace_tags 仅含 pre/textarea，非 <pre> 容器里的「纯空白文本节点」
# 会在解析阶段就丢掉行首缩进（实测 "\n    " -> "\n"），据此产出会**静默篡改代码**，
# 比不识别更糟。真实站点（Pygments/Rouge/Prism/Highlight.js）的代码都在 <pre> 内，
# 故 <pre> 已足够覆盖。

def inline(node):
    parts = []
    for ch in node.children:
        if isinstance(ch, NavigableString):
            parts.append(str(ch))
        elif isinstance(ch, Tag):
            if ch.name in ('strong', 'b'):
                t = inline(ch)
                parts.append(f'**{t}**' if t.strip() else t)
            elif ch.name in ('em', 'i'):
                t = inline(ch)
                parts.append(f'*{t}*' if t.strip() else t)
            elif ch.name == 'br':
                parts.append(' ')
            elif ch.name == 'code':
                parts.append('`' + ch.get_text() + '`')
            elif ch.name == 'img':
                n = IMG_IDX.get(id(ch))
                if n and n not in DROP and not (0 < img_width(ch) <= 100):
                    parts.append(f'[[IMG:{IMG_SEQ[n - 1][2]}]]')
            else:
                parts.append(inline(ch))
    return ''.join(parts)

out = []

# build_md 会用 meta 标题生成 `# 标题`；若正文首个 <h1> 与标题重复，此处跳过，避免出现两个同名一级标题
_TITLE_KEY = re.sub(r'\s+', '', meta.get('title') or '')
_state = {'title_h1_used': False}

def walk(node):
    for ch in node.children:
        if not isinstance(ch, Tag):
            if isinstance(ch, NavigableString):
                t = norm(str(ch))
                if t:
                    out.append(t)
            continue
        if ch.name in ('script', 'style', 'mp-style-type', 'br'):
            continue
        if ch.name == 'img':
            n = IMG_IDX.get(id(ch))
            if n is None or n in DROP or (0 < img_width(ch) <= 100):
                continue
            out.append(f'[[IMG:{IMG_SEQ[n - 1][2]}]]')
            continue
        if ch.name == 'pre':
            txt = code_text(ch).replace('\u200b', '').replace('\xa0', ' ')
            lines = [l.rstrip() for l in txt.split('\n')]
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()
            out.append('[CODE:%s]' % code_lang(ch) + '\n'.join(lines) + '[/CODE]')
            continue
        if ch.name == 'table':
            rows = []
            for tr in ch.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    c = re.sub(r'\s+', ' ', norm(inline(td))).strip()
                    cells.append(c.replace('|', '\\|'))  # 单元格内管道符转义，避免破表
                rows.append('| ' + ' | '.join(cells) + ' |')
            if rows:
                out.append('[TABLE]' + '\n'.join(rows) + '[/TABLE]')
            continue
        if ch.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            t = norm(inline(ch))
            if t:
                if (ch.name == 'h1' and not _state['title_h1_used']
                        and _TITLE_KEY and re.sub(r'\s+', '', t) == _TITLE_KEY):
                    _state['title_h1_used'] = True
                    continue
                out.append('#' * min(int(ch.name[1]), 6) + ' ' + t)
            continue
        if ch.name in ('ul', 'ol'):
            for i, li in enumerate(ch.find_all('li', recursive=False), 1):
                t = norm(inline(li))
                if t:
                    out.append((f'{i}. ' if ch.name == 'ol' else '- ') + t)
            continue
        if ch.name == 'blockquote':
            t = norm(inline(ch))
            if t:
                out.append('> ' + t)
            continue
        if ch.name == 'figure':
            if ch.find('img') is not None:
                walk(ch)
            else:
                t = norm(inline(ch))
                if t:
                    out.append(t)
            continue
        if ch.find(list(BLOCK)) is not None:
            walk(ch)
            continue
        t = norm(inline(ch))
        if t:
            out.append(t)

walk(content)
text = '\n\n'.join(out)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('=== META ===\n')
    f.write(json.dumps(meta, ensure_ascii=False, indent=1) + '\n')
    f.write('=== BODY ===\n')
    f.write(text + '\n')

print('meta:', json.dumps({k: v for k, v in meta.items()
                           if k not in ('images_auto_dropped', 'ad_candidates')},
                          ensure_ascii=False))
print('content root:', root_sel, '| html cache:', os.path.basename(cache_file))
print('blocks:', len(out))
print('img placeholders:', len(re.findall(r'\[\[IMG:', text)))
print('CODE blocks:', text.count('[CODE:'))
print('auto-dropped imgs:', json.dumps(auto_dropped, ensure_ascii=False))
print('ad candidates (需用 Read 看图确认，确认后加 --drop):')
for c in candidates:
    print('  IMG %02d w=%s ratio=%s | %s' % (c['index'], c['w'], c['ratio'], ' ；'.join(c['reasons'])))
if suspect_code:
    print('!! 疑似代码容器但不在 <pre> 内（缩进可能已丢失，请对照原文核对或标【存疑】）:')
    for s in suspect_code:
        print('  <%s class="%s"> %s' % (s['tag'], s['class'], s['preview']))
