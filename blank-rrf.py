# -*- coding: utf-8 -*-
"""
空白页默写训练 —— rrf_fuse（RRF 融合）
日期：2026-09-27 上午（月考 1 前的最后自检）

规则（硬）：
  1. 闭卷。不翻 hybrid_rerank.py、不翻 rrf-语法详解.md。
  2. 写完先自己打勾自检判据，再跑下面的 diff。
  3. 差异不算失败，算读数 —— 重点问「逻辑不同还是写法不同」。

跑 diff：
  diff <(sed -n '67,91p' "G:/agent学习/week7/hybrid_rerank.py") "G:/agent学习/week7/blank-rrf.py"
"""

# 与本训练无关，仅为让本文件可独立 import；常量真值在 hybrid_rerank.py
RRF_K = 60


# ══════════════════════════════════════════════════════════════════════
#  ★ 你写：RRF 融合（约 6 行）
# ══════════════════════════════════════════════════════════════════════
def rrf_fuse(vec_ids, bm25_ids, k=RRF_K):
    """把两路检索结果**按名次**融合成一个列表。

    RRF（Reciprocal Rank Fusion）：
        score(id) = Σ_over_lists  1 / (k + rank)      rank 从 1 开始，不是 0

    为什么用名次不用分数：**两路的分数不可比**（cosine 相似度 0~1，BM25 是无上界实数）。
    名次是两路唯一可比的量。

    参数：vec_ids / bm25_ids 都是**已按好坏排好序**的 id 列表（可能长度不同、可能重复）
    返回：融合后**按分数降序**的 id 列表（去重）

    自检判据（写完自己打勾，别先看源码）：
      [ ] rank 从 1 起（enumerate(xs, 1)），不是 0
      [ ] 遍历的是**两榜并集**（set(a) | set(b)），不是只有向量榜
      [ ] **缺榜 = 贡献 0** —— 用 dict.get() 判 None，没上榜的那一路不加分
      [ ] 排序键是**分数**（scores.get），**降序**
      [ ] 返回的是 **id 列表**，不是 dict、不是 tuple
    """
    # ------------------------------------------------------------------
    # TODO: 你来写（约 6 行）
    # 提示：
    #   第 1 步 —— 把两路 id 列表各转成 {id: 名次} 的字典（名次从 1 起）
    #   第 2 步 —— 准备一个空的分数容器
    #   第 3 步 —— 遍历「两榜并集」，对每路查名次：查到了就累加 1/(k+rank)，查不到就跳过（贡献 0）
    #   第 4 步 —— 按分数降序返回 id 列表
    # ------------------------------------------------------------------
    rerank_vec = {doc_id: r for r,doc_id in enumerate(vec_ids,1)}
    rerank_bm25 = {doc_id: r for r,doc_id in enumerate(bm25_ids,1)}

    scores ={}
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
#  自检小跑（写完后直接 `python blank-rrf.py`；期望读数已注明）
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 场景：两路各 3 个 id，有一半重叠，长度还不同 —— 专门验「并集 + 缺榜贡献 0」
    vec = ["a", "b", "c"]
    bm25 = ["c", "d", "a"]

    try:
        fused = rrf_fuse(vec, bm25, k=60)
    except NotImplementedError:
        print("[待写] rrf_fuse 还是空的，先把它写出来。")
        raise SystemExit(0)

    # 手算校验（k=60）：
    #   a: 向量 rank1 → 1/61 , BM25 rank3 → 1/63   → 合计 ≈ 0.032269
    #   b: 向量 rank2 → 1/62 , BM25 缺席 → 0       → 合计 ≈ 0.016129
    #   c: 向量 rank3 → 1/63 , BM25 rank1 → 1/61   → 合计 ≈ 0.032269
    #   d: 向量缺席 → 0      , BM25 rank2 → 1/62   → 合计 ≈ 0.016129
    # 期望：a 与 c 分数相同（居前），b 与 d 分数相同（居后）。集合必须含全部 4 个 id。
    print("fused =", fused)
    print("len  =", len(fused), "(应为 4 = 两榜并集大小)")

    got = set(fused)
    assert got == {"a", "b", "c", "d"}, f"并集不对：{got}"
    assert fused[0] in ("a", "c") and fused[-1] in ("b", "d"), f"排序可疑：{fused}"
    print("[OK] 并集正确 + 排序正确 —— 自检通过")
