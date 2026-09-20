# -*- coding: utf-8 -*-
"""
embed_base64.py — 把 Markdown 里的本地图片引用替换为 Base64 data URI。

用法:
  python embed_base64.py <article.md>

行为:
  - 扫描 md 中所有 ![alt](path) 图片引用。
  - 若 path 是本地存在的文件（非 http/https/data），读取并替换为
    ![alt](data:image/<ext>;base64,<内容>) —— 使单文件 md 自包含、零外链。
  - 若本地文件不存在（下载失败），替换为 【存疑】[图：alt 未获取到]【/存疑】。
  - 已是 http/https/data 的引用原样保留（正常情况下不应出现）。
原地覆盖写回原 md 文件，并打印替换统计。
"""
import sys
import os
import re
import base64

MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "svg": "image/svg+xml",
}

IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _embed_match(m, base_dir):
    alt, path = m.group(1), m.group(2).strip()
    if path.startswith(("http://", "https://", "data:")):
        return m.group(0)  # 远程/已内嵌，保留
    local = path
    if not os.path.isabs(local):
        local = os.path.join(base_dir, local)
    if os.path.exists(local):
        ext = os.path.splitext(local)[1].lstrip(".").lower()
        mime = MIME.get(ext, "image/png")
        with open(local, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return "![%s](data:%s;base64,%s)" % (alt, mime, b64)
    # 下载失败 / 文件缺失 → 标存疑（包裹式）
    return "【存疑】[图：%s 未获取到]【/存疑】" % (alt or path)


def main():
    if len(sys.argv) < 2:
        print("usage: embed_base64.py <article.md>")
        sys.exit(1)
    md_path = sys.argv[1]
    base_dir = os.path.dirname(os.path.abspath(md_path))
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    n_img = 0
    n_embed = 0
    n_fail = 0

    def repl(m):
        nonlocal n_img, n_embed, n_fail
        n_img += 1
        out = _embed_match(m, base_dir)
        if out.startswith("【存疑】"):
            n_fail += 1
        elif "data:" in out:
            n_embed += 1
        return out

    new_text = IMG_RE.sub(repl, text)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(new_text)

    size = os.path.getsize(md_path)
    print("图片引用=%d 已内嵌=%d 失败标存疑=%d 新md大小=%d"
          % (n_img, n_embed, n_fail, size))


if __name__ == "__main__":
    main()
