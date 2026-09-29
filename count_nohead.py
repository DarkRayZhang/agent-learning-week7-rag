# -*- coding: utf-8 -*-
"""Q3 收尾 · B 索引里那 100 个「无标题块」到底是什么？

跑法（**PowerShell 5.1 不认 `&&`，必须分两条命令**）：
    cd G:\\agent学习\\week7
    ..\\week5\\.venv\\Scripts\\python.exe count_nohead.py

0 次 API 调用 —— 只读磁盘上已有的 B 索引。
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chromadb

HERE = os.path.dirname(os.path.abspath(__file__))
WEEK5 = os.path.normpath(os.path.join(HERE, "..", "week5"))
DOCS_DIR = os.path.join(WEEK5, "docs")
COLLECTION_B = "ab_section"

client = chromadb.PersistentClient(path=os.path.join(WEEK5, "chroma_db"))
col = client.get_collection(COLLECTION_B)

n = col.count()
got = col.get(include=["documents", "metadatas"], limit=n)
docs = got["documents"]
metas = got["metadatas"]

no_head = [(m, d) for m, d in zip(metas, docs) if d.count("## ") == 0]
with_head = [d for d in docs if d.count("## ") >= 1]
md_files = sorted(p for p in os.listdir(DOCS_DIR) if p.endswith(".md"))

print("=" * 74)
print("Q3 收尾 · B 索引里的「无标题块」")
print("=" * 74)
print(f"  B 总块数               = {n}")
print(f"  含 `## ` 的小节块       = {len(with_head)}")
print(f"  无标题块                = {len(no_head)}")
print(f"  语料篇数（docs/*.md）   = {len(md_files)}")
print()
same = "相等 ← 这不是巧合" if len(no_head) == len(md_files) else "不相等"
print(f"  ★ 无标题块 {len(no_head)}  ｜  语料篇数 {len(md_files)}  → {same}")
print()

print("── 这 100 个块长什么样（前 3 个，原文照打）──")
for i, (m, d) in enumerate(no_head[:3], 1):
    print(f"\n  [{i}] metadata = {m}")
    print(f"      长度 {len(d)} 字 ｜ 含 '## ' {d.count('## ')} 次 ｜ 原文：")
    for ln in d.splitlines():
        print(f"        {ln!r}")

lens = sorted(len(d) for _m, d in no_head)
print()
print("── 长度分布 ──")
print(f"  min {lens[0]} ｜ 中位 {lens[len(lens) // 2]} ｜ max {lens[-1]}"
      f" ｜ 平均 {sum(lens) // len(lens)}")

tot = sum(len(d) for d in docs)
sub_tot = sum(len(d) for d in with_head)
print()
print("── Q2 ④ 的证据：97 字这个平均，是被谁拉低的 ──")
print(f"  全部 {n} 块         总和 {tot} 字 → 平均 {tot // n} 字")
print(f"  剔除废块后 {len(with_head)} 块  总和 {sub_tot} 字 → 平均 {sub_tot // len(with_head)} 字")
print(f"  （对照：A 策略平均 344 字／块）")
