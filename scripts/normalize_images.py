#!/usr/bin/env python3
"""把目录内全部图片统一为 WebP，并限制最大边 1600px。

用法:
    python normalize_images.py <images_dir> [md_file]

规则:
    - 所有图片统一转为 WebP（quality=98，支持透明背景，不合成白底）。
    - 动图（GIF/APNG/动态 WebP 等多帧图片）保留动画，转为动态 WebP（逐帧缩放/转模式，
      帧时长与循环次数沿用源图）。
    - 高或宽任一超过 1600px 时，按最长边 1600 等比缩小（LANCZOS）。
    - 统一命名 <原文件名去后缀>.webp，旧文件删除。
    - 若给出 md_file，把 md 里的 images/xxx.<旧后缀> 引用同步替换为 images/xxx.webp。
    - 逐张输出转换/缩放明细，便于向用户汇报。
"""
import re
import sys
from pathlib import Path

from PIL import Image

MAX_SIDE = 1600
QUALITY = 98  # WebP 有损压缩质量


def to_webp_mode(im: Image.Image) -> Image.Image:
    """转成 WebP 支持的模式，保留透明通道。"""
    if im.mode == "P":
        return im.convert("RGBA" if "transparency" in im.info else "RGB")
    if im.mode in ("RGB", "RGBA", "L", "LA"):
        return im
    # CMYK / YCbCr / I / F / 1 等非常规模式
    has_alpha = im.mode in ("PA",) or (
        "transparency" in im.info and im.mode not in ("CMYK",)
    )
    return im.convert("RGBA" if has_alpha else "RGB")


def convert_animated(im: Image.Image, out: Path, scale: float) -> tuple:
    """多帧动图：逐帧转模式/缩放后存为动态 WebP，保留动画。返回 (新宽, 新高, 是否缩小)。
    out 与源文件同路径时先写临时文件再替换（避免边读边写截断源文件）。
    注意：逐帧 seek 后 im.info 不再携带 transparency 标记，须在 seek 前记录并逐帧统一应用，
    否则动图透明背景会丢失。"""
    has_transparency = (
        im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    )
    frames = []
    durations = []
    w, h = im.size
    for i in range(im.n_frames):
        im.seek(i)
        if im.mode == "P":
            f = im.convert("RGBA" if has_transparency else "RGB")
        else:
            f = to_webp_mode(im)
        # 必须复制成独立静态图像：若直接持有源 GIF 的 Image 对象（seek 后可能已是 RGBA、
        # 带 n_frames），PIL _save_all 会按 n_frames 重复展开该帧，导致帧数/时长错乱
        f = f.copy()
        if scale < 1:
            f = f.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        frames.append(f)
        durations.append(im.info.get("duration", 100))
    tmp = out.with_suffix(".webp.tmp")
    frames[0].save(
        tmp, "WEBP", save_all=True, append_images=frames[1:],
        duration=durations, loop=im.info.get("loop", 0), quality=QUALITY,
    )
    if out.exists():
        try:
            out.unlink()
        except OSError as e:
            print(f"[warn] {out.name}: 旧文件删除失败（{e}），已用新文件覆盖目标")
            tmp.replace(out)  # 覆盖目标，忽略残留
            nw, nh = frames[0].size
            return nw, nh, scale < 1
    tmp.replace(out)
    nw, nh = frames[0].size
    return nw, nh, scale < 1


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: normalize_images.py <images_dir> [md_file]")
        sys.exit(1)
    img_dir = Path(sys.argv[1])
    if not img_dir.is_dir():
        print(f"[error] 目录不存在: {img_dir}")
        sys.exit(1)
    md = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    renames = []  # (old_name, new_name)
    for p in sorted(img_dir.iterdir()):
        if not p.is_file():
            continue
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print(f"[skip] {p.name}: 无法作为图片打开 ({e})，保持原样")
            continue
        w, h = im.size
        alpha_kept = im.mode in ("RGBA", "LA") or (
            im.mode == "P" and "transparency" in im.info
        )
        n_frames = getattr(im, "n_frames", 1)
        scale = MAX_SIDE / max(w, h) if max(w, h) > MAX_SIDE else 1.0
        if n_frames > 1:
            nw, nh, shrunk = convert_animated(im, img_dir / (p.stem + ".webp"), scale)
            shrunk = " -> 缩小" if shrunk else ""
            new_name = p.stem + ".webp"
            anim = f" [动图 {n_frames} 帧]"
        else:
            im = to_webp_mode(im)
            shrunk = ""
            if scale < 1:
                im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
                shrunk = " -> 缩小"
            new_name = p.stem + ".webp"
            out = img_dir / new_name
            im.save(out, "WEBP", quality=QUALITY)
            nw, nh = im.size
            anim = ""
        if p.name != new_name and p.exists():
            try:
                p.unlink()
            except OSError as e:
                print(f"[warn] {p.name}: 旧文件删除失败（{e}），保留残留文件（md 引用已指向 {new_name}，不影响结果）")
        renames.append((p.name, new_name))
        alpha = " [透明保留]" if alpha_kept else ""
        print(f"[ok] {p.name} -> {new_name}  {w}x{h} -> {nw}x{nh}{shrunk}{anim}{alpha}")

    if md is not None and md.is_file():
        text = md.read_text(encoding="utf-8")
        changed = 0
        for old, new in renames:
            stem = Path(old).stem
            old_ext = Path(old).suffix  # 含点，如 ".png"
            if old == new:
                continue
            pattern = re.compile(
                r"(images/" + re.escape(stem) + re.escape(old_ext) + r")"
            )
            text, n = pattern.subn("images/" + new, text)
            changed += n
        md.write_text(text, encoding="utf-8")
        print(f"[md] {md.name}: 同步更新 {changed} 处图片引用")
    elif md is not None:
        print(f"[warn] md 文件不存在，未同步引用: {md}")


if __name__ == "__main__":
    main()
