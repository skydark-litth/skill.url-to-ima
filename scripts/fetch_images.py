# -*- coding: utf-8 -*-
"""
fetch_images.py — 抓取网页正文中的图片并下载到本地，输出 URL→本地相对路径映射。

用法:
  python fetch_images.py <page_url> <out_images_dir> <mapping_json>

要点（与 extract_article.py 强一致）:
  - 正文根定位、懒加载取值、图片编号**全部复用 article_common.py**，与 extract_article.py
    共用同一份 DOM 缓存（raw_<hash>.html），保证「第 N 张图」文件名 img_0N 与
    extract_article.py 的 --drop 序号严格对应。
  - 懒加载取值优先级：data-src / data-original / … 优先，src 垫底（避免抓到 1x1 占位图）。
  - 装饰图（声明宽度 <= 100px）只占号不下载，记为 ok=false / reason=decorative。
  - 内联 data: 图片不落地，ordered 里 file=该 data URI（供 build_md 直接内嵌）。
  - 下载失败的原图记为 ok=false（供调用方标"存疑"），绝不静默丢弃。
  - 输出 mapping.json: {"page_url","count","mapping":{原src:文件名|null},"ordered":[{index,src,file,alt,ok}]}
"""
import sys
import os
import json
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from article_common import (UA, load_or_fetch_html, find_content_root,
                            img_sequence, img_width)

TIMEOUT = 25
_VALID_EXT = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg")


def _ext_of(url):
    p = urllib.parse.urlparse(url).path
    ext = os.path.splitext(p)[1].lstrip(".").lower()
    return ext if ext in _VALID_EXT else "png"


def _download(abs_url, fpath, referer):
    req = urllib.request.Request(
        abs_url, headers={"User-Agent": UA, "Referer": referer, "Accept": "image/*,*/*"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    with open(fpath, "wb") as f:
        f.write(data)
    return len(data)


def main():
    if len(sys.argv) < 4:
        print("usage: fetch_images.py <page_url> <out_images_dir> <mapping_json>")
        sys.exit(1)

    page_url, out_dir, mapping_json = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    workdir = os.path.dirname(os.path.abspath(out_dir))

    try:
        html, cache_file = load_or_fetch_html(page_url, workdir)
    except Exception as e:
        print("PAGE_FETCH_FAIL:", e)
        with open(mapping_json, "w", encoding="utf-8") as f:
            json.dump({"page_url": page_url, "count": 0, "mapping": {},
                       "ordered": [], "page_error": str(e)}, f, ensure_ascii=False, indent=2)
        sys.exit(0)

    soup = BeautifulSoup(html, "lxml")
    content, root_sel = find_content_root(soup)
    seq = img_sequence(content)

    mapping = {}
    ordered = []
    done = {}  # src -> 已下载文件名（同一 src 重复出现时复用，避免重复下载）

    for n, img, src in seq:
        alt = (img.get("alt") or "").strip()
        w = img_width(img)

        if src.startswith("data:"):
            mapping[src] = src  # 已是内嵌，交给 build_md 直接输出
            ordered.append({"index": n, "src": src, "file": src, "alt": alt,
                            "ok": True, "reason": "inline-data-uri"})
            print("DATA %02d  (内联 data URI，不落地)" % n)
            continue

        if 0 < w <= 100:
            mapping[src] = None
            ordered.append({"index": n, "src": src, "file": None, "alt": alt,
                            "ok": False, "reason": "decorative"})
            print("SKIP %02d  w=%d  装饰图（不下载）" % (n, w))
            continue

        if src in done:
            fname = done[src]
            mapping[src] = fname
            ordered.append({"index": n, "src": src, "file": fname, "alt": alt,
                            "ok": True, "reason": "reused"})
            print("REUSE%02d  %s" % (n, fname))
            continue

        abs_url = urllib.parse.urljoin(page_url, src)
        fname = "img_%02d.%s" % (n, _ext_of(abs_url))
        fpath = os.path.join(out_dir, fname)
        try:
            size = _download(abs_url, fpath, page_url)
            mapping[src] = fname
            done[src] = fname
            ordered.append({"index": n, "src": src, "file": fname, "alt": alt, "ok": True})
            print("OK   %02d  %s  ->  %s  (%d bytes)" % (n, abs_url, fname, size))
        except Exception as e:
            mapping[src] = None
            ordered.append({"index": n, "src": src, "file": None, "alt": alt,
                            "ok": False, "reason": str(e)})
            print("FAIL %02d  %s  ->  %s" % (n, abs_url, e))

    n_ok = len([o for o in ordered if o["ok"] and not str(o["file"]).startswith("data:")])
    with open(mapping_json, "w", encoding="utf-8") as f:
        json.dump({"page_url": page_url, "content_root": root_sel,
                   "count": len(ordered), "downloaded": n_ok,
                   "mapping": mapping, "ordered": ordered}, f, ensure_ascii=False, indent=2)
    print("DONE content_root=%s total=%d downloaded=%d -> %s"
          % (root_sel, len(ordered), n_ok, mapping_json))


if __name__ == "__main__":
    main()
