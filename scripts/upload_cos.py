# -*- coding: utf-8 -*-
"""
url-to-ima 配套：将本地文件上传到 ima 的 COS 存储桶。
用法：python upload_cos.py <cos_credential.json> <本地文件路径>
  cos_credential.json : create_media 返回的 cos_credential 对象（整个写进文件）
  <本地文件路径>       : 要上传的 docx / pdf 等
使用官方 cos-python-sdk-v5，不要手写签名（手写会稳定 403）。
"""
import sys, os, json
from qcloud_cos import CosConfig, CosS3Client

CONTENT_TYPE = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "md": "text/markdown",
    "txt": "text/plain",
}


def main():
    if len(sys.argv) != 3:
        print("USAGE: python upload_cos.py <cos_credential.json> <local_file>")
        sys.exit(2)
    creds_path, local_path = sys.argv[1], sys.argv[2]
    creds = json.load(open(creds_path, encoding="utf-8"))

    # 显式校验凭证结构：最常见的错误是 cred.json 多包了一层 {"cos_credential": {...}} 外壳。
    if "cos_credential" in creds and "region" not in creds:
        print("ERROR: cred.json 多包了一层 cos_credential 外壳。"
              "请直接写入该对象内部的字段（region/secret_id/secret_key/token/bucket_name/cos_key）。")
        sys.exit(2)
    missing = [k for k in ("region", "secret_id", "secret_key", "token",
                           "bucket_name", "cos_key") if not creds.get(k)]
    if missing:
        print("ERROR: cred.json 缺少必需字段: %s" % ", ".join(missing))
        sys.exit(2)

    config = CosConfig(
        Region=creds["region"],
        SecretId=creds["secret_id"],
        SecretKey=creds["secret_key"],
        Token=creds["token"],
        Scheme="https",
    )
    client = CosS3Client(config)

    ext = os.path.splitext(local_path)[1].lstrip(".").lower()
    ctype = CONTENT_TYPE.get(ext, "application/octet-stream")

    with open(local_path, "rb") as f:
        resp = client.put_object(
            Bucket=creds["bucket_name"],
            Body=f,
            Key=creds["cos_key"],
            ContentType=ctype,
        )
    etag = resp.get("ETag")
    size = os.path.getsize(local_path)
    print("UPLOAD_OK:", bool(etag), "ETag:", etag, "bytes:", size)
    sys.exit(0 if etag else 1)


if __name__ == "__main__":
    main()
