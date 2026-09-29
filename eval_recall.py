# -*- coding: utf-8 -*-
"""
Week 7 · 周三 ②：检索质量评测（只测**检索层**，不调 LLM）
==========================================================

【为什么不用 W6 那 30 条端到端用例】
  它把「检索失败」和「生成失败」搅在一起 → 分不清病在哪。
  本脚本**只测 R（检索）** → 一个数，与生成无关。

【三个指标各测什么（两个正交维度）】
  ┌─ 召回类（找没找到）── hit@k ／ recall@k
  └─ 排序类（排得多靠前）── MRR ★

  | 指标      | 公式                        | 分母        | 本语料下有区分度？        |
  |----------|----------------------------|------------|------------------------|
  | hit@k    | Top-k 里**有没有**命中        | 无          | ⚠️ 容易顶格              |
  | recall@k | 命中数 / 相关总数             | **相关总数** | ❌ 上限 = k/分母 ≈ 33%   |
  | MRR      | 首个命中块的 1/rank 的平均     | **无**      | ✅ **有**               |

  ⚠️ 关键读数纪律：**先算指标的物理上限，再看数**。
     分母 15 而 k=5 → recall@5 上限 33% → 跑出来 30% 不是"系统不行"，是"指标选错"。
     （同族：09-26 题 14「判据低估了系统」）

【粒度：块级（和 W6 / chunking_ab.py 口径一致）】
  golden 集里存的是**文档名**（离线可复现），本脚本**先映射到块 id** 再评测。
  → 「定义」与「用哪个索引」解耦：换 B 组（645 块）评时，golden 定义不用改。

【跑法】在 week7/ 目录下（**先跑 golden_set.py**）：
    ..\\week5\\.venv\\Scripts\\python.exe eval_recall.py --no-embed
"""
import argparse
import json
import os
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

import chromadb                       # noqa: E402

GOLDEN_PATH = os.path.join(HERE, "golden_set.json")
Q_CACHE = os.path.join(HERE, "recall_q_cache.json")   # ⚠️ 和 20 题的缓存分开（题不同）
PERSIST_DIR = os.path.join(WEEK5, "chroma_db")
COLLECTION = "week5_docs"             # A 组（200 块，固定 500/50 切）—— 和 W6 同口径
K_LIST = (1, 3, 5)
TOP_N = max(K_LIST)                   # 一次查到 5，喂给三个 k


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 1：文档名 → 块 id 映射（你来写，约 6~8 行）
# ══════════════════════════════════════════════════════════════════════
def build_doc_to_chunks(metas, ids):
    """把「文档名 → 属于它的块 id 列表」建出来。

    入参：
        metas —— Chroma `col.get(...)` 返回的 metadatas 列表（**和 ids 一一对应、同序**）
                 每个 meta 形如 {"source": "doc_007.md", "chunk_index": 3}
        ids   —— 同一批块的 id 列表（**下标与 metas 对齐**）

    出参：
        {"doc_007.md": ["chunk_000123", "chunk_000124", ...], ...}

    ⚠️ 这里就是「**契约 vs 实现**」那把尺子：
        golden 集里存的是**文档名**（人类可读、离线可复现），
        评测时需要的却是**块 id**（Chroma 的主键）—— 两者必须显式映射，不能隐式假设相等。

    判据（4 条）：
      ① 用 `enumerate(metas)` 拿下标，`ids[i]` 才拿得到对应的块 id（**别用 zip 也行，但要同序**）
      ② **默认值用 `[]`，不是 `None`** —— 用 `setdefault(name, [])` 或 `defaultdict(list)`
         （用 `None` 的话后面 `.append` 直接炸；用 `get(name, [])` 又拿不到同一份 list）
      ③ 同一个 doc 的块 id **保持原顺序**（`col.get` 返回的顺序 = 入库顺序，可用于人工核对）
      ④ 返回的 dict 里**键必须覆盖所有文档**（别过滤，宁可有空列表）

    提示（3 步）：
      1. `out = {}`
      2. `for i, m in enumerate(metas): name = m["source"]` （若 `source` 缺失用 `m.get("source", "?")`）
      3. `out.setdefault(name, []).append(ids[i])`   ← ★ 这一行是全部核心
    """
    out = {}
    for i, m in enumerate(metas):
        name = m["source"]
        if name is not None:
           out.setdefault(name,[]).append(ids[i])    
    return out


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 2：MRR（你来写，约 6~8 行）
# ══════════════════════════════════════════════════════════════════════
def reciprocal_rank(retrieved_ids, relevant_ids):
    """算**一题**的 RR（Reciprocal Rank，MRR 的单个样本）。

    定义：
        找到**第一个**命中的位置 → 取倒数 1/rank（rank 从 1 起）
            rank=1 → 1.0      排第 1
            rank=2 → 0.5      排第 2
            rank=3 → 0.33
        一个都没命中 → **0.0**

    入参：
        retrieved_ids —— 检索返回的**有序**块 id 列表
        relevant_ids  —— golden 映射后的**相关块 id**（无序，可能为空）

    判据（4 条，**每条都会咬人**）：
      ① **找到第一个就 return，不要继续遍历**（`return` 不是 `break`+事后处理）
      ② rank 从 **1** 起（`enumerate(xs, 1)`）—— 写成 0 起的话 1/0 直接炸
      ③ **一个都没命中 → 返回 0.0**（不是 None！MRR 里"没命中"就是 0 分，
         这点和 recall 不同 —— recall 的 0 分母是"无定义"，MRR 的 0 分母不存在）
      ④ 用 `set(relevant_ids)` 包一层再判成员（列表的 `in` 是 O(n)，集合是 O(1)）

    提示（3 步）：
      1. `rel = set(relevant_ids)`，若空直接 `return 0.0`
      2. `for rank, rid in enumerate(retrieved_ids, 1):`
      3. `if rid in rel: return 1.0 / rank`   →  循环外 `return 0.0`

    Java 对照：这就是"首个正确结果的位置"的倒数 —— 和你评估搜索/推荐排序质量是同一种思路。
    """
    rel = set(relevant_ids)
    if not rel:
        return 0.0
    for rank, rid in enumerate(retrieved_ids,1):
        if rid in rel:
            return 1.0 / rank
    return 0.0


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 3：单题评测（你来写，约 10~14 行）
# ══════════════════════════════════════════════════════════════════════
def eval_one_query(col, qvec, item, doc2chunks, k_list=K_LIST):
    """检索一次，把**三指标**一次算全。

    入参：
        col        —— Chroma collection
        qvec       —— 问题向量
        item       —— golden 集里的一条 dict（含 query / relevant(文档名) / category）
        doc2chunks —— build_doc_to_chunks 的产物
        k_list     —— 要算的 k（1/3/5）

    出参：
        {"num":..., "query":..., "category":..., "n_relevant_docs":...,
         "n_relevant_chunks":...,                      # ★ 新分母（块数，会远大于 k）
         "retrieved_ids": [...],                       # 有序块 id（Top-5）
         "per_k": {1: {"hit":..., "recall":...}, 3: {...}, 5: {...}},
         "rr": 0.5}                                    # reciprocal rank

    ⚠️ **关键坑（今晚第二扇闸门）**：Chroma 返回的 `ids` 是**块 id**，
        而 golden 里存的是**文档名** —— **必须先经过 doc2chunks 映射**，
        直接把 `ids` 和 `item["relevant"]` 求交 → **恒等于 0，且脚本不报错**。
        （这就是昨晚那个"自检假绿"的同款：跑通了、有输出了、结果全错）

    判据（5 条）：
      ① 只查一次，`n_results=TOP_N`（别对每个 k 查一遍）
      ② 检索结果要 `include=["metadatas"]` 吗？—— **不用**！本函数只需要 `ids`
         （映射关系已由 doc2chunks 预先建好，检索出来直接是块 id）
      ③ 相关块集合 = 把 `item["relevant"]`（文档名列表）里每个文档的块**并起来**：
         `rel_chunks = [c for name in item["relevant"] for c in doc2chunks.get(name, [])]`
         → 注意这可能是**很长的列表**（十几个块），因为分母是块级
      ④ per_k 里：`hit = 1 if (Top-k 与 rel_chunks 有交集) else 0`
                    `recall = |Top-k ∩ rel_chunks| / len(rel_chunks)`
         → **hit@k 和 recall@k 分母不同**：hit 不看分母，recall 看 `n_relevant_chunks`
      ⑤ 拒答题（relevant 为空 → rel_chunks 为空）→ recall 返回 **None**（不参与平均），
         hit 返回 0，rr 返回 0.0

    提示（4 步）：
      1. `res = col.query(query_embeddings=[qvec], n_results=TOP_N)`
         `ids = res["ids"][0]`
      2. 组装 `rel_chunks`（见判据③）
      3. `per_k = {}` → 对每个 k：切片 `ids[:k]`，算 hit 与 recall（复用你上面写好的函数思路）
      4. 返回 dict；`rr = reciprocal_rank(ids, rel_chunks)`（若 rel_chunks 空则 0.0）
    """
    res = col.query(query_embeddings=[qvec], n_results=TOP_N)   # ⚠️ n_results（带 s）
    ids  = res["ids"][0]
    rel_chunks = [c for name in item["relevant"] for c in doc2chunks.get(name,[])]
    rel_set = set (rel_chunks)

    per_k ={}
    for k in k_list:
        top_k = ids[:k]
        hit = 1 if (set(top_k) & rel_set) else 0
        if not rel_set:
           recall = None 
        else:
           recall = len(set(top_k) & rel_set) / len(rel_set)
        per_k[k] = {"hit":hit,"recall":recall}
    return{
        "num":item["num"], 
        "query":item["query"], 
        "category":item["category"], 
        "n_relevant_docs": item["n_relevant"],
        "n_relevant_chunks":len(rel_chunks),                      # ★ 新分母（块数，会远大于 k）
        "retrieved_ids": ids,                       # 有序块 id（Top-5）
        "per_k": per_k,
        "rr": reciprocal_rank(ids, rel_chunks)}


# ══════════════════════════════════════════════════════════════════════
#  工具：问题向量化（我写好了）
# ══════════════════════════════════════════════════════════════════════
def get_query_vecs(queries, use_cache=True):
    if use_cache and os.path.exists(Q_CACHE):
        with open(Q_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        if len(cache) == len(queries):
            print(f"[embed] 复用缓存 {Q_CACHE}（0 次 API）")
            return cache
    from embed_batch import embed_batch
    print(f"[embed] {len(queries)} 个问题向量化中（{(len(queries)+9)//10} 次 API）...")
    t0 = time.time()
    vecs = embed_batch(queries, batch_size=10, delay=0.12, max_retry=3, verbose=True)
    print(f"[embed] 完成 {time.time()-t0:.1f}s")
    if use_cache:
        with open(Q_CACHE, "w", encoding="utf-8") as f:
            json.dump(vecs, f)
    return vecs


# ══════════════════════════════════════════════════════════════════════
#  汇总（我写好了）—— 三指标 + 分母列，把"上限"直接打在表上
# ══════════════════════════════════════════════════════════════════════
def summarize(rows, k_list=K_LIST):
    lines = []
    scored = [r for r in rows if r["n_relevant_chunks"] > 0]
    refused = [r for r in rows if r["n_relevant_chunks"] == 0]

    lines.append(f"{'类别':<5} {'题数':>4} {'平均分母':>8} " +
                 " ".join(f"{'hit@'+str(k):>7} {'rec@'+str(k):>7}" for k in k_list) +
                 f" {'MRR':>7} {'上限*':>7}")
    lines.append("-" * 96)
    for cat in ["正常", "多跳", "全体"]:
        group = scored if cat == "全体" else [r for r in scored if r["category"] == cat]
        if not group:
            continue
        avg_den = sum(r["n_relevant_chunks"] for r in group) / len(group)
        cells = []
        for k in k_list:
            h = sum(r["per_k"][k]["hit"] for r in group) / len(group)
            c_vals = [r["per_k"][k]["recall"] for r in group
                      if r["per_k"][k]["recall"] is not None]
            c = sum(c_vals) / len(c_vals) if c_vals else float("nan")
            cells.append(f"{h:>7.1%} {c:>7.1%}")
        mrr = sum(r["rr"] for r in group) / len(group)
        ceil = min(1.0, k_list[-1] / avg_den) if avg_den else 0.0
        tag = "  ← 基线" if cat == "全体" else ""
        lines.append(f"{cat:<5} {len(group):>4} {avg_den:>8.1f} " +
                     " ".join(cells) + f" {mrr:>7.3f} {ceil:>7.1%}{tag}")

    lines.append("")
    lines.append("* 上限 = k/平均分母（分母 ≫ k 时，recall@k 物理上就上不去 → 看 MRR）")
    if refused:
        lines.append("")
        lines.append(f"[拒答题 {len(refused)} 条] 分母为 0 → recall 无定义（不参与平均）；"
                     f"看**误召回**：")
        for r in refused:
            lines.append(f"    #{r['num']:>2} {r['query'][:16]:<16} "
                         f"Top-{TOP_N} 里块 id {r['retrieved_ids'][:2]}…（无参考集，只看是否稳定）")
    return lines


# ══════════════════════════════════════════════════════════════════════
#  main —— 我写好了（含**两扇闸门**）
# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embed", action="store_true", help="复用问题向量缓存")
    args = ap.parse_args()

    if not os.path.exists(GOLDEN_PATH):
        print(f"❌ 找不到 {GOLDEN_PATH} → 先跑 golden_set.py")
        sys.exit(2)
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)
    print(f"golden set 已载入：{len(golden)} 条")

    client = chromadb.PersistentClient(path=PERSIST_DIR)
    col = client.get_collection(COLLECTION)
    print(f"索引已载入：{COLLECTION}（{col.count()} 块）\n")

    # ── 载入全部块 → 建「文档名 → 块 id」映射 ──
    got = col.get(include=["metadatas"], limit=col.count())
    doc2chunks = build_doc_to_chunks(got["metadatas"], got["ids"])
    print(f"[映射] {len(doc2chunks)} 个文档 → {sum(len(v) for v in doc2chunks.values())} 块")

    # ══ 闸门 1：命名空间对齐 ══════════════════════════════════════════
    print("=" * 74)
    print("闸门 1 · 命名空间对齐（这一步不过，全量结果全是 0 且不报错）")
    print("=" * 74)
    miss = [g["num"] for g in golden if g["relevant"]
            and not any(n in doc2chunks for n in g["relevant"])]
    if miss:
        print(f"  ❌ 这几题的 relevant 文档名在索引里找不到：{miss}")
        print("     → 检查 golden 是文档级、索引 metadatas 里有没有 source")
    else:
        print("  ✅ golden 里的文档名**都能在索引 metadatas 的 source 里找到**")

    # ══ 闸门 2：先跑第 1 题，两边的 id 打出来对一眼 ════════════════════
    qvecs = get_query_vecs([g["query"] for g in golden], use_cache=not args.no_embed)
    probe = eval_one_query(col, qvecs[0], golden[0], doc2chunks)
    print(f"\n  题 #{probe['num']} {probe['query']}")
    print(f"  相关块数（新分母）：{probe['n_relevant_chunks']}  "
          f"（文档数 {probe['n_relevant_docs']}）")
    print(f"  检索 Top-{TOP_N} 块 id：{probe['retrieved_ids']}")
    print(f"  相关块 id（前 5）  ：{[c for n in golden[0]['relevant'][:2] for c in doc2chunks.get(n, [])][:5]}")
    print(f"  本题 hit@1/@3/@5 = "
          f"{probe['per_k'][1]['hit']}/{probe['per_k'][3]['hit']}/{probe['per_k'][5]['hit']}"
          f" ｜ RR = {probe['rr']:.3f}")

    # ══ 全量 ══════════════════════════════════════════════════════════
    print("\n" + "=" * 74)
    print(f"全量评测 · {len(golden)} 题 · 三指标 · 只测检索层（0 次 LLM）")
    print("=" * 74)
    rows = [eval_one_query(col, qv, item, doc2chunks) for item, qv in zip(golden, qvecs)]

    print(f"\n{'#':>3} {'类别':<4} {'分母':>5}  {'hit@1':>6} {'hit@3':>6} {'hit@5':>6}  "
          f"{'rec@5':>7} {'RR':>6}  {'提问':<16}")
    print("-" * 104)
    for r in rows:
        c5 = r["per_k"][5]["recall"]
        print(f"{r['num']:>3} {r['category']:<4} {r['n_relevant_chunks']:>5}  "
              f"{r['per_k'][1]['hit']:>6} {r['per_k'][3]['hit']:>6} {r['per_k'][5]['hit']:>6}  "
              f"{('  —  ' if c5 is None else f'{c5:>7.1%}')} {r['rr']:>6.3f}  {r['query'][:16]:<16}")

    lines = ["Week 7 · 检索质量评测（h it@k / recall@k / MRR，只测检索层）",
             "=" * 62, ""]
    lines.extend(summarize(rows))
    lines.append("")
    lines.append("【口径】粒度为**块级**（与 week6 / chunking_ab.py 一致）")
    lines.append("  hit@k    = Top-k 里有没有命中（无分母）")
    lines.append("  recall@k = |Top-k ∩ 相关块| / |相关块|（分母 = 该题相关块总数）")
    lines.append("  MRR      = 首个命中块 1/rank 的平均（无分母，看排序质量）")
    lines.append("  拒答题分母为 0 → recall 无定义（None），不参与平均")
    out = os.path.join(HERE, "eval_recall_result.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n" + "\n".join(lines))
    print(f"\n→ 已落盘 {out}")


if __name__ == "__main__":
    main()
