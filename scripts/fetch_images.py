# -*- coding: utf-8 -*-
"""
fetch_images.py — 抓取网页中的图片并下载到本地，输出 URL→本地相对路径映射。

用法:
  python fetch_images.py <page_url> <out_images_dir> <mapping_json>

说明:
  - 解析所有 <img>，兼容 src / data-src / data-original / data-lazy-src 懒加载属性。
  - 相对路径用 page_url 补全为绝对地址。
  - 逐张下载到 out_images_dir，文件名按 img_01.png / img_02.jpg ... 顺序命名。
  - 已内嵌的 data: 图片保持原样，不下载。
  - 下载失败的原图在 mapping 中记为 null（供调用方标"存疑"）。
  - 输出 mapping.json: {"page_url":..., "count":N, "mapping":{原src: 本地文件名或null}}
"""
import sys
import os
import json
import urllib.request
import urllib.parse
import urllib.error
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 25
_VALID_EXT = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg")


def _fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": url})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


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

    try:
        html = _fetch_html(page_url)
    except Exception as e:
        print("PAGE_FETCH_FAIL:", e)
        # 仍写出空 mapping，让调用方知道整页图片抓取失败
        with open(mapping_json, "w", encoding="utf-8") as f:
            json.dump({"page_url": page_url, "count": 0, "mapping": {},
                       "page_error": str(e)}, f, ensure_ascii=False, indent=2)
        sys.exit(0)

    soup = BeautifulSoup(html, "lxml")
    mapping = {}
    ordered = []
    seen = set()
    i = 0

    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or img.get("data-original")
               or img.get("data-lazy-src") or "").strip()
        alt = (img.get("alt") or "").strip()
        if not src:
            continue
        if src.startswith("data:"):
            mapping[src] = src  # 已是内嵌，保持原样
            ordered.append({"src": src, "file": src, "alt": alt, "ok": True})
            continue
        abs_url = urllib.parse.urljoin(page_url, src)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        i += 1
        fname = "img_%02d.%s" % (i, _ext_of(abs_url))
        fpath = os.path.join(out_dir, fname)
        try:
            size = _download(abs_url, fpath, page_url)
            mapping[src] = fname  # 相对 images/ 目录的文件名
            ordered.append({"src": src, "file": fname, "alt": alt, "ok": True})
            print("OK   %02d  %s  ->  %s  (%d bytes)" % (i, abs_url, fname, size))
        except Exception as e:
            mapping[src] = None  # 下载失败，调用方标"存疑"
            ordered.append({"src": src, "file": None, "alt": alt, "ok": False})
            print("FAIL %02d  %s  ->  %s" % (i, abs_url, e))

    with open(mapping_json, "w", encoding="utf-8") as f:
        json.dump({"page_url": page_url, "count": i, "mapping": mapping,
                   "ordered": ordered}, f, ensure_ascii=False, indent=2)
    print("DONE total=%d mapping=%s" % (i, mapping_json))


if __name__ == "__main__":
    main()
