# -*- coding: utf-8 -*-
"""
Week 7 · rerank + 混合检索 —— **针对今天的失败清单做的定点修复**
==================================================================

> 今天的失败清单（09-26 实测）就是今晚的**验收清单**：
>
> | 索引 | 基线 | 失败题 | 病 | 药 |
> |---|---|---|---|---|
> | **A** 200 块（固定 500/50） | hit@1 17/20 | 题 1 / 12 / 14 | 候选**在 Top-3 里**、排不到第一 | **rerank** |
> | **B** 645 块（按小节） | hit@3 19/20 | 题 8（14 个正确答案全被挤出） | **召回缺失** | **BM25 融合** |
>
> 跑法（在 week7/ 目录下，用 week5 的 venv）：
>     ..\\week5\\.venv\\Scripts\\python.exe hybrid_rerank.py
>     ..\\week5\\.venv\\Scripts\\python.exe hybrid_rerank.py --no-embed   # 复用缓存的问题向量
>
> ⚠️ 两个函数**留空给你写**（`rrf_fuse` / `rerank_rule`）—— 未实现时会**降级只跑基线**，
>    所以你可以**先跑一次看基线，再填函数看提升**。
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEEK5 = os.path.normpath(os.path.join(HERE, "..", "week5"))
sys.path.insert(0, WEEK5)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np                      # noqa: E402
import chromadb                         # noqa: E402
from rank_bm25 import BM25Okapi         # noqa: E402

from chunking_ab import CASES           # noqa: E402  ← 20 题复用，不再维护第二份

PERSIST_DIR = os.path.join(WEEK5, "chroma_db")
COLLECTION_A = "week5_docs"             # 固定长度 500/50，200 块
COLLECTION_B = "ab_section"             # 按 markdown 小节，645 块
CAND_K = 10                             # 第一阶段候选宽度（rerank 的输入）
TOP_K = 3                               # 最终交付宽度（和 baseline 可比）
RRF_K = 60                              # RRF 的平滑常数（论文默认 60）
Q_CACHE = os.path.join(HERE, "query_vec_cache.json")


# ══════════════════════════════════════════════════════════════════════
#  中文分词 —— 用字符 bigram，**不引入 jieba**
#  ── 理由（正好是你今晚学的"成本形态"）：jieba 是**结构期成本**（多一个依赖 + 词典加载），
#     而中文关键短语用 bigram 已经能原样命中（"健康检查"→ 健康/康检/检查）。
# ══════════════════════════════════════════════════════════════════════
def tokenize_zh(text, n=2):
    t = text.replace("\n", " ").strip()
    if len(t) <= n:
        return [t] if t else []
    return [t[i:i + n] for i in range(len(t) - n + 1)]


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 1：RRF 融合（你来写，约 6 行）
# ══════════════════════════════════════════════════════════════════════
def rrf_fuse(vec_ids, bm25_ids, k=RRF_K):
    """把两路检索结果**按名次**融合成一个列表。

    RRF（Reciprocal Rank Fusion）：
        score(id) = Σ_over_lists  1 / (k + rank)      rank 从 1 开始，不是 0

    为什么用名次不用分数：**两路的分数不可比**（cosine 相似度 0~1，BM25 是无上界实数）。
    名次是两路唯一可比的量。

    参数：vec_ids / bm25_ids 都是**已按好坏排好序**的 id 列表（可能长度不同、可能重复）
    返回：融合后**按分数降序**的 id 列表（去重）
    """
    rerank_vec = {doc_id: r for r,doc_id in enumerate(vec_ids,1)}
    rerank_bm25 ={doc_id: r for r,doc_id in enumerate(bm25_ids,1)}
    scores = {}
    for doc_id in set(vec_ids) | set(bm25_ids):
        total = 0.0
        r = rerank_vec.get(doc_id)
        if r is not None:
            total += 1.0 / (k+r)
        r = rerank_bm25.get(doc_id)
        if r is not None:
            total += 1.0 / (k+r)
        scores[doc_id] = total
    return sorted(scores,key=scores.get,reverse=True)


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 2：规则重排（你来写，约 10 行）
# ══════════════════════════════════════════════════════════════════════
def rerank_rule(query, docs):
    """用**零成本规则**把候选块重新排序（不上模型的 rerank）。

    提示：先算一个"匹配分"，再按分降序。
      ① 命中数：query 的 bigram 里，有多少个在这个块里出现过
      ② 覆盖率：命中数 / query 的 bigram 总数（防止"长块天然占便宜"）
      ③ 连续命中加分：query 的 bigram 在原句里**连续**出现（说明是短语、不是散词）

    参数：query 是问题字符串；docs 是候选块文本列表（**已按向量分排好序**）
    返回：重排后的 docs 列表（长度不变）
    ⚠️ 验收要求：修好 A 的题 1 / 12 / 14（它们现在排不到第一）
    """

    q_set = set(tokenize_zh(query))
    scored = []
    for rank,doc in enumerate(docs):
        hit =len(q_set & set(tokenize_zh(doc)))
        scored.append((hit, -rank,doc))
    scored.sort(key= lambda t:(t[0],t[1]),reverse=True)    
    return [t[2] for t in scored]


# ══════════════════════════════════════════════════════════════════════
#  工具：向量 + BM25 两路检索
# ══════════════════════════════════════════════════════════════════════
def load_collection(client, name):
    col = client.get_collection(name)
    got = col.get(include=["documents"], limit=col.count())
    return col, got["ids"], got["documents"]


def bm25_rank(bm25, ids, query, k=CAND_K):
    scores = bm25.get_scores(tokenize_zh(query))
    order = np.argsort(scores)[::-1][:k]
    return [ids[i] for i in order]


def get_query_vecs(cases, use_cache=True):
    if use_cache and os.path.exists(Q_CACHE):
        with open(Q_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        if len(cache) == len(cases):
            print(f"[embed] 复用缓存 {Q_CACHE}（0 次 API）")
            return cache
    from embed_batch import embed_batch
    print(f"[embed] 20 个问题向量化中（2 次 API）...")
    t0 = time.time()
    vecs = embed_batch([c[1] for c in cases], batch_size=10, delay=0.12,
                       max_retry=3, verbose=True)
    print(f"[embed] 完成 {time.time()-t0:.1f}s")
    if use_cache:
        with open(Q_CACHE, "w", encoding="utf-8") as f:
            json.dump(vecs, f)
    return vecs


# ══════════════════════════════════════════════════════════════════════
#  实验 1：A 索引 + rerank（治"排不到第一"）
# ══════════════════════════════════════════════════════════════════════
def exp_a_rerank(col, qvecs):
    print("\n" + "=" * 74)
    print("实验 1 · A 索引（200 块）· 单向量 vs +rerank")
    print("=" * 74)
    rows, ok_before, ok_after = [], 0, 0
    impl = True

    for (num, q, key, _src), qv in zip(CASES, qvecs):
        res = col.query(query_embeddings=[qv], n_results=CAND_K)
        docs = res["documents"][0]
        hit_before = key in docs[0]

        try:
            re_docs = rerank_rule(q, docs)
            hit_after = key in re_docs[0]
        except NotImplementedError:
            impl = False
            re_docs, hit_after = docs, hit_before

        ok_before += hit_before
        ok_after += hit_after
        rows.append((num, q, key, hit_before, hit_after,
                     docs.index(next(d for d in docs if key in d)) + 1 if any(key in d for d in docs) else None))

    print(f"  单向量 Top-1 命中： **{ok_before}/20**")
    if impl:
        print(f"  +规则重排 Top-1 ： **{ok_after}/20**   （提升 {ok_after-ok_before:+d}）")
    else:
        print(f"  ⏸  rerank_rule 未实现 → 只跑了基线")

    print(f"\n  三个『排不到第一』的题（今天的失败清单）：")
    for num, q, key, hb, ha, pos in rows:
        if num in (1, 12, 14):
            print(f"    #{num:<2} {q:<12} 单向量Top-1 {'✅' if hb else '🔶'} ｜ "
                  f"正确答案原本排第 {pos} ｜ 重排后Top-1 {'✅' if ha else '🔶'}")
    return ok_before, ok_after, impl, rows


# ══════════════════════════════════════════════════════════════════════
#  实验 2：B 索引 + BM25 融合（治"召回缺失"）
# ══════════════════════════════════════════════════════════════════════
def exp_b_hybrid(col, ids, docs, qvecs):
    print("\n" + "=" * 74)
    print("实验 2 · B 索引（645 块）· 单向量 vs +BM25 融合")
    print("=" * 74)
    doc_of = dict(zip(ids, docs))
    bm25 = BM25Okapi([tokenize_zh(d) for d in docs])

    rows, ok_before3, ok_after3 = [], 0, 0
    impl = True

    for (num, q, key, _src), qv in zip(CASES, qvecs):
        # ⚠️ 两路**必须取同样的宽度**（都 CAND_K=10），否则 RRF 融合不公平：
        #    候选多的那一路会有更多"得分机会" —— 和 rerank 里"不加覆盖率、长块占便宜"是同一类毛病。
        res = col.query(query_embeddings=[qv], n_results=CAND_K)
        v_ids_wide = res["ids"][0]
        hit_before3 = any(key in doc_of[i] for i in v_ids_wide[:TOP_K])   # 基线 = 向量前 3 个

        b_ids = bm25_rank(bm25, ids, q, k=CAND_K)
        try:
            fused = rrf_fuse(v_ids_wide, b_ids)[:TOP_K]
            hit_after3 = any(key in doc_of[i] for i in fused)
        except NotImplementedError:
            impl = False
            hit_after3 = hit_before3

        ok_before3 += hit_before3
        ok_after3 += hit_after3
        rows.append((num, q, key, hit_before3, hit_after3))

    print(f"  单向量 Top-3 命中： **{ok_before3}/20**")
    if impl:
        print(f"  +BM25 融合 Top-3： **{ok_after3}/20**   （提升 {ok_after3-ok_before3:+d}）")
    else:
        print(f"  ⏸  rrf_fuse 未实现 → 只跑了基线")

    print(f"\n  那一道『彻底召回不到』的题（今天的失败清单）：")
    for num, q, key, hb, ha in rows:
        if num == 8:
            print(f"    #{num} {q}")
            print(f"      期望含：{key}")
            print(f"      单向量 Top-3 {'✅' if hb else '❌'} ｜ 融合后 Top-3 {'✅' if ha else '❌'}")

    # 顺带看看 BM25 单独一路能不能打到题 8
    for (num, q, key, _src) in CASES:
        if num == 8:
            b_ids = bm25_rank(bm25, ids, q, k=CAND_K)
            n_hit = sum(1 for i in b_ids if key in doc_of[i])
            print(f"      🔎 BM25 单独一路 Top-{CAND_K} 里有 **{n_hit}** 个块含该短语"
                  f"（全库共 {sum(1 for d in docs if key in d)} 个）")
    return ok_before3, ok_after3, impl, rows


# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embed", action="store_true", help="复用缓存的问题向量")
    args = ap.parse_args()

    client = chromadb.PersistentClient(path=PERSIST_DIR)
    col_a, ids_a, docs_a = load_collection(client, COLLECTION_A)
    col_b, ids_b, docs_b = load_collection(client, COLLECTION_B)
    print(f"索引已载入：A {len(ids_a)} 块 ｜ B {len(ids_b)} 块")

    qvecs = get_query_vecs(CASES, use_cache=not args.no_embed)

    ab, aa, impl_a, rows_a = exp_a_rerank(col_a, qvecs)
    bb, ba, impl_b, rows_b = exp_b_hybrid(col_b, ids_b, docs_b, qvecs)

    lines = ["Week 7 · rerank + 混合检索（定点修复今天的失败清单）", "=" * 62, ""]
    lines.append(f"实验 1｜A 索引 + rerank（治'排不到第一'）")
    lines.append(f"  单向量 Top-1 {ab}/20 → 重排后 Top-1 {aa}/20" + ("" if impl_a else "  ⏸ 函数未实现"))
    lines.append("")
    lines.append(f"实验 2｜B 索引 + BM25 融合（治'召回缺失'）")
    lines.append(f"  单向量 Top-3 {bb}/20 → 融合后 Top-3 {ba}/20" + ("" if impl_b else "  ⏸ 函数未实现"))
    lines.append("")
    lines.append("【验收清单 = 今天的失败清单】")
    lines.append("  A: 题 1 / 12 / 14  从 🔶 变 ✅ ？")
    lines.append("  B: 题 8          从 ❌ 变 ✅ ？")
    out = os.path.join(HERE, "hybrid_rerank_result.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n" + "\n".join(lines))
    print(f"\n→ 已落盘 {out}")


if __name__ == "__main__":
    main()
