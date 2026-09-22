# -*- coding: utf-8 -*-
"""url-to-ima 共用工具：HTML 抓取与缓存、正文根定位、图片序列与懒加载取值。

本模块被 extract_article.py 与 fetch_images.py 共用。**共用是刻意设计**：
两者对「第 N 张图」的编号必须完全一致，agent 才能按文件名 img_0N 看图后用
`extract_article.py --drop N` 精确排除广告图。此前两个脚本各自维护一套取图/编号
逻辑（内容根不同、懒加载属性优先级不同、编号基准不同），在非公众号页面上必然错位。

适配范围：微信公众号（#js_content）以及其他常见文章页（article / main / 常见正文容器）。
"""
import hashlib
import os
import re
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
TIMEOUT = 30

# 正文容器候选（按优先级）。
CONTENT_SELECTORS = [
    '#js_content',                                  # 微信公众号
    '.rich_media_content',                          # 微信公众号（外层）
    '#js_article', '.RichText',                     # 知乎
    '.markdown-body',                               # GitHub / 掘金 等
    '.article-content', '.article_content', '.article-body', '.article__body',
    '.post-content', '.post-body', '.post__content',
    '.entry-content', '.entry-text', '.rich_media_area_primary_inner',
    '#article-content', '#articleContent', '#content', '.content',
    'article', 'main',
]

# 懒加载取值优先级：真实图优先，占位图（常在 src 里）垫底。
SRC_ATTRS = ('data-src', 'data-original', 'data-actualsrc', 'data-lazy-src',
             'data-original-src', 'data-echo', 'data-croporisrc', 'src')

# 常见 1x1 占位图 data URI，不能当作真实图片
_PLACEHOLDER = re.compile(
    r'^data:image/(?:gif|png|jpeg|jpg);base64,(?:R0lGOD|iVBORw0KGgoAAAANSUhEUgAAAAE)',
    re.I,
)


def origin_of(url):
    """取 URL 的 scheme://netloc，用作 Referer（公众号自动得到 mp.weixin.qq.com）。"""
    p = urllib.parse.urlparse(url)
    return '%s://%s/' % (p.scheme, p.netloc) if p.netloc else url


def cache_path(url, cache_dir):
    """按 URL 哈希命名缓存文件，避免同一临时目录下多篇文章互相覆盖。"""
    h = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
    return os.path.join(cache_dir, 'raw_%s.html' % h)


def load_or_fetch_html(url, cache_dir, force=False):
    """读取或抓取 HTML，并落盘缓存。

    两个脚本共用同一缓存：先跑谁，后跑的直接复读，保证二者解析的是**同一份 DOM**，
    图片编号因此严格一致；同时规避微信短时间重复抓取的限流。
    """
    cp = cache_path(url, cache_dir)
    if os.path.exists(cp) and not force:
        with open(cp, encoding='utf-8') as f:
            return f.read(), cp
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': origin_of(url),
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        enc = r.headers.get_content_charset()
    if not enc:
        m = re.search(rb'charset\s*=\s*["\']?\s*([\w-]+)', raw[:8192], re.I)
        enc = m.group(1).decode('ascii', 'replace') if m else 'utf-8'
    html = raw.decode(enc, 'replace')
    os.makedirs(cache_dir, exist_ok=True)
    with open(cp, 'w', encoding='utf-8') as f:
        f.write(html)
    return html, cp


def find_content_root(soup):
    """定位正文容器，返回 (element, 选择器名)。非公众号页面靠候选+启发式兜底。"""
    for sel in CONTENT_SELECTORS:
        try:
            el = soup.select_one(sel)
        except Exception:
            continue
        if el is not None and el.find('img') is not None:
            return el, sel
        if el is not None and len(el.get_text(strip=True)) >= 200:
            return el, sel

    # 兜底：在 <article>/<section>/<div> 里选「文本足够多且结构最紧凑」的容器，
    # 避免选到包裹全站导航的巨型 div（会引入大量无关图片）。
    best, best_len = None, 0
    for el in soup.find_all(['article', 'section', 'div']):
        if el.find('img') is None:
            continue
        L = len(el.get_text(strip=True))
        if L < 200:
            continue
        if L > best_len:
            best, best_len = el, L
    if best is None:
        return (soup.body or soup), 'body'
    tight = best
    tight_n = len(best.find_all(True))
    for el in soup.find_all(['article', 'section', 'div']):
        if el.find('img') is None:
            continue
        L = len(el.get_text(strip=True))
        if L >= best_len * 0.5 and len(el.find_all(True)) < tight_n:
            tight, tight_n = el, len(el.find_all(True))
    return tight, 'heuristic'


def pick_src(tag):
    """按统一优先级取图片真实地址；过滤 1x1 占位 data URI。"""
    for a in SRC_ATTRS:
        v = (tag.get(a) or '').strip()
        if v and not _PLACEHOLDER.match(v):
            return v
    ss = (tag.get('srcset') or '').strip()
    if ss:
        first = ss.split(',')[0].strip().split(' ')[0].strip()
        if first and not _PLACEHOLDER.match(first):
            return first
    return ''


def img_width(tag):
    """图片声明宽度（px）：兼容公众号 data-w、width 属性与 style。取不到返回 0。"""
    for a in ('data-w', 'width'):
        v = re.sub(r'[^\d]', '', str(tag.get(a) or ''))
        if v:
            return int(v)
    m = re.search(r'width\s*:\s*(\d+)', tag.get('style') or '')
    return int(m.group(1)) if m else 0


def img_sequence(root):
    """正文内按文档顺序的图片序列，返回 [(index, tag, src)]，index 从 1 开始。

    仅收录能取到 src 的 <img>；**两端脚本共用此函数**，故 --drop 序号与
    fetch_images.py 的文件编号天然一致。装饰图（宽度<=100px）也占号，
    以保证编号不发生位移（它们在输出阶段才被剔除）。
    """
    seq = []
    for im in root.find_all('img'):
        s = pick_src(im)
        if s:
            seq.append((len(seq) + 1, im, s))
    return seq


def img_index_map(root):
    """返回 (id(tag)->index, seq)，供遍历时反查序号。"""
    seq = img_sequence(root)
    return {id(t): n for n, t, _ in seq}, seq


def meta_map(soup):
    """收集 <meta> 的 name/property -> content，用于通用元信息提取。"""
    d = {}
    for m in soup.find_all('meta'):
        k = (m.get('property') or m.get('name') or '').strip().lower()
        v = (m.get('content') or '').strip()
        if k and v and k not in d:
            d[k] = v
    return d


def page_meta(soup):
    """通用页面元信息：标题 / 作者 / 发布时间（非公众号页面用）。"""
    d = meta_map(soup)
    title = d.get('og:title') or d.get('twitter:title') or ''
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h = soup.find(['h1'])
        title = h.get_text(strip=True) if h else ''
    author = (d.get('author') or d.get('article:author')
              or d.get('og:article:author') or '')
    publish = (d.get('article:published_time') or d.get('og:release_date')
               or d.get('og:updated_time') or d.get('date') or '')
    if not publish:
        t = soup.find('time')
        if t is not None:
            publish = (t.get('datetime') or t.get_text(strip=True) or '')
    return {'title': title, 'author': author, 'publish': publish}
