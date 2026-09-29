# -*- coding: utf-8 -*-
"""
Week 7 周一 · 切块策略 A/B（20 题版）
=====================================

跑法（在 week7/ 目录下，用 week5 的 venv）：
    ..\\week5\\.venv\\Scripts\\python.exe chunking_ab.py --validate   # ① 只校验短语，0 次 API
    ..\\week5\\.venv\\Scripts\\python.exe chunking_ab.py              # ② 跑 A/B 20 题

【和 W5 那版（week5/compare_chunking.py）的关系 —— 不重写，只扩 + 修坑】
  ① CASES 8 → 20 题。**原有 8 题一字不动** —— 它是基线，改了就没法跨周比较。
  ② 新增第三列「**混杂块占比**」（W5 那次 70% vs 0% 是人工统计的，这次做成脚本输出）。
  ③ 修坑：W5 版用 os.chdir + 相对路径，只能在 week5/ 里跑；本版用 __file__ 定位，从哪跑都行。
     （week7/ 没有自己的 venv，所以用 week5 的 venv —— 但工作目录是 week7/，
      .env 会从 week7/.env 读，那份是 09-26 从 week6/.env 复制过来的完整版。）
  ④ 加 --validate：**先确认"关键短语真能在语料里原样找到"再花钱**。
     （W6 那 30 条用例就栽在这 —— 8 条判据指向语料里根本没有的内容。）
  ⑤ B 索引已存在就**复用**（W5 版每次都 delete + 全量重 embed，645 块 ≈ 65 次 API 调用，白花钱）。

【判定口径（沿用 W5，不许改）】
  命中 = Top-K 的块文本里含该题的**关键短语**（能在语料里原样找到的那个片段）。
  hit@1 = Top-1 就含；hit@3 = 前三里任意一块含。

【这一版要回答的两个问题（= week7/notes.md 周一节）】
  Q1 哪条命中率高？—— 跑完看 hit@1 / hit@3
  Q2 **代价是什么？** —— 看「块数 / 平均块长 / 混杂块占比」这三列（B 不是白赢的）
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEEK5 = os.path.normpath(os.path.join(HERE, "..", "week5"))
PERSIST_DIR = os.path.join(WEEK5, "chroma_db")
DOCS_DIR = os.path.join(WEEK5, "docs")
sys.path.insert(0, WEEK5)          # 让 embed_batch 可导入

import chromadb                     # noqa: E402

COLLECTION_A = "week5_docs"        # 固定长度 500/50（build_index.py 建的）
COLLECTION_B = "ab_section"        # 按 markdown 小节切
TOP_K = 3

# ══════════════════════════════════════════════════════════════════════════
#  20 题清单
#  ── 格式：(题号, 提问, 关键短语, 出处小节)
#  ── 第 9~20 题的短语 = None，是留给你填的（见下面「怎么填」）
# ══════════════════════════════════════════════════════════════════════════
CASES = [
    # ① 原有 8 题（W5 加餐版基线，**一字不动**）
    (1,  "周报什么时候交",         "每周五 17:00 前提交",              "日程/交周报"),
    (2,  "发版前必须确认什么",     "回滚方案",                         "发布值班/发版窗口"),
    (3,  "空调滤网多久洗一次",     "空调滤网每月洗一次",               "生活采买/家电维护"),
    (4,  "缓存穿透怎么处理",       "查不到的数据也要缓存一个空值",     "编程运维/缓存穿透"),
    (5,  "会议纪要多久发出来",     "会议纪要 24 小时内发出",           "日程/部门周会"),
    (6,  "跑步一次跑多远",         "5 公里起步",                       "健康作息/跑步计划"),
    (7,  "护照有效期要求",         "护照有效期必须剩 6 个月以上",      "出行旅行/护照签证"),
    (8,  "健康检查接口为什么必须加", "会把还没起来的实例也算进负载",   "编程运维/部署健康检查"),

    # ② 新增 12 题 —— 短语留空，你来填
    #    ⚠️ 判据地基：短语必须能在 week5/docs/ 里**原样找到**（连标点都要对）
    #    填法：短语去 week5/make_docs.py 的 ENTRIES 里找（对应「出处小节」那一栏）
    #          填完跑 `--validate`，脚本会告诉你每一句在多少篇文档里出现
    ( 9, "灰度怎么放量",           "先放 1% 流量", "发布值班/灰度策略"),
    (10, "事故复盘要产出什么",     "时间线、根因、可落地的改进项及负责人", "发布值班/事故复盘"),
    (11, "数据库备份保留多久",     "30 天", "编程运维/数据库备份"),
    (12, "幂等键放在哪",           "请求头里", "编程运维/接口幂等"),
    (13, "什么情况该用警告级别",   "可以自动重试或降级恢复", "编程运维/日志分级"),
    (14, "睡眠目标是什么",         "目标 23:30 前躺下，睡够 7 小时，睡前 1 小时不看短视频", "健康作息/睡眠"),
    (15, "久坐怎么缓解",           "每工作 50 分钟起来活动 5 分钟", "健康作息/久坐对策"),
    (16, "述职材料怎么写",         "要拿数据说话", "日程/季度述职"),
    (17, "代码评审会什么时候开",   "每周三 15:00", "日程/代码评审会"),
    (18, "国内航班要提前多久到",   "提前 2 小时到", "出行旅行/机场值机"),
    (19, "酒店怎么选",             "选地铁站 800 米以内的", "出行旅行/酒店选择"),
    (20, "生鲜什么时候买",         "每周六上午去菜市场", "生活采买/生鲜采购"),
]

# 「好短语」的判据 —— --validate 按这个分档
# 【09-26 晚修正】原写 DISCRIMINATIVE_MAX = 20（拍脑袋定的）→ 实测证明偏紧：
#   「灰度策略」小节在 100 篇里被抽中 21 篇（= 100% 覆盖），21 篇完全正常。
#   语料构造决定了**一个小节最多出现在 ~33 篇**（63 篇 → 小节覆盖率）。
#   → 篇数只反映"这句在小节里的覆盖率"（多 = 题目更容易），
#     **真正决定判据好坏的是「纯度」：短语只能出现在目标小节里**。
DISCRIMINATIVE_MAX = 30    # 超过 30 篇 ≈ 一个小节能覆盖的极限，值得看一眼
CHUNK_OVERLAP_A = 50       # A 策略的重叠字符数（build_index.py 的 CHUNK_OVERLAP）


def sections_of(body):
    """把一篇文档拆成 [(小节标题, 小节正文), ...]"""
    out = []
    for line in body.splitlines():
        if line.startswith("## "):
            out.append([line[3:].strip(), []])
        elif out:
            out[-1][1].append(line)
    return [(t, "\n".join(b)) for t, b in out]


def purity_of(corpus, key, target_section):
    """纯度：含该短语的小节，是不是**只有目标小节**？

    这是比"出现篇数"更硬的判据 —— 短语若同时出现在别的小节里，
    检索命中的可能压根不是你要的那块（判据有歧义，测出来的数不可信）。
    """
    found = {}
    for _name, body in corpus:
        for title, text in sections_of(body):
            if key in text:
                found[title] = found.get(title, 0) + 1
    wrong = {t: c for t, c in found.items() if t != target_section}
    return found, wrong


# ── 语料侧：短语在多少篇文档里原样出现 ──────────────────────────────────
def load_corpus():
    docs = []
    for path in sorted(os.listdir(DOCS_DIR)):
        if path.endswith(".md"):
            with open(os.path.join(DOCS_DIR, path), encoding="utf-8") as f:
                docs.append((path, f.read()))
    return docs


def validate_cases(corpus):
    """纯离线校验：0 次 API。这是 W6 那 30 条用例的教训 —— 先验判据，再跑评测。

    三条一起看：
      ① 存在性：短语能不能在语料里原样找到（找不到 = 判据错）
      ② **纯度**：含短语的小节是不是**只有目标小节**（跨小节 = 判据有歧义）★
      ③ 长度：短语长度 > overlap(50) 时会有"掉进缝里"的风险（A 策略）
    """
    print("=" * 78)
    print("关键短语校验（离线，0 次 API）")
    print("=" * 78)
    print(f"语料：{len(corpus)} 篇 ｜ A 策略 overlap = {CHUNK_OVERLAP_A} 字\n")

    unfilled = [c for c in CASES if c[2] is None]
    bad = []
    for num, q, key, src in CASES:
        if key is None:
            print(f"  ⬜ {num:>2}  {q:<16} —— 短语未填（出处：{src}）")
            continue
        hits = [name for name, body in corpus if key in body]
        n = len(hits)
        target = src.split("/")[-1]
        found, wrong = purity_of(corpus, key, target)

        if n == 0:
            mark, note = "❌", "**语料里找不到这句话** → 判据错，不是系统错（W6 同款坑）"
            bad.append(num)
        elif wrong:
            mark, note = "⚠️", f"**跨小节**：还出现在 {list(wrong)} → 判据有歧义"
            bad.append(num)
        elif n > DISCRIMINATIVE_MAX:
            mark, note = "⚠️", f"出现在 {n} 篇（> {DISCRIMINATIVE_MAX}，值得看一眼）"
        else:
            mark, note = "✅", f"出现在 {n} 篇"

        length_warn = ""
        if len(key) > CHUNK_OVERLAP_A:
            length_warn = f"  ⚠️ 短语 {len(key)} 字 > overlap {CHUNK_OVERLAP_A} → 可能掉进切缝"

        print(f"  {mark} {num:>2}  {q:<16} 「{key}」")
        print(f"        └─ {note} ｜ 纯度：{found}{length_warn}")

    print()
    if unfilled:
        print(f"→ ⬜ 未填 {len(unfilled)} 题：{[c[0] for c in unfilled]}")
    if bad:
        print(f"→ ❌ 需修判据 {len(bad)} 题：{bad}")
    if not unfilled and not bad:
        print("→ ✅ 20 题全部就绪（存在性 + 纯度都过），可以跑 `chunking_ab.py`")
    return not unfilled and not bad



# ── 索引侧：块体量 + 混杂块占比 ────────────────────────────────────────
def collection_stats(col, tag):
    """混杂块 = 一个块里含 ≥2 个 `## ` 标题 → 跨了语义边界（教训：hit@1 会骗人）"""
    n = col.count()
    got = col.get(include=["documents"], limit=n)
    docs = got["documents"]
    mixed = sum(1 for d in docs if d.count("## ") >= 2)
    no_head = sum(1 for d in docs if d.count("## ") == 0)
    lens = [len(d) for d in docs]
    return {
        "tag": tag, "chunks": n, "avg_len": sum(lens) // n,
        "min_len": min(lens), "max_len": max(lens),
        "mixed": mixed, "mixed_pct": round(mixed * 100 / n, 1),
        "no_head": no_head, "no_head_pct": round(no_head * 100 / n, 1),
    }


def print_stats(s):
    print(f"  [{s['tag']}] 块数 {s['chunks']} ｜ 平均 {s['avg_len']} 字"
          f"（{s['min_len']}~{s['max_len']}）｜ **混杂块 {s['mixed']} ({s['mixed_pct']}%)**"
          f" ｜ 无标题块 {s['no_head']} ({s['no_head_pct']}%)")


# ── 主流程 ─────────────────────────────────────────────────────────────
def build_section_index():
    """按 markdown 小节切 → 建 B 索引。已存在则复用（除非 --rebuild-b）。"""
    import glob
    from embed_batch import embed_batch

    def chunk_by_section(text):
        blocks, cur = [], []
        for line in text.splitlines():
            if line.startswith("## "):
                if cur:
                    blocks.append("\n".join(cur).strip())
                cur = [line]
            else:
                cur.append(line)
        if cur:
            blocks.append("\n".join(cur).strip())
        return [b for b in blocks if b]

    client = chromadb.PersistentClient(path=PERSIST_DIR)
    try:
        client.delete_collection(COLLECTION_B)
    except Exception:
        pass
    col = client.get_or_create_collection(COLLECTION_B, metadata={"hnsw:space": "cosine"})

    texts, metas = [], []
    for path in sorted(glob.glob(os.path.join(DOCS_DIR, "*.md"))):
        with open(path, encoding="utf-8") as f:
            body = f.read()
        for blk in chunk_by_section(body):
            title = blk.splitlines()[0].replace("## ", "").strip()
            texts.append(blk)
            metas.append({"source": os.path.basename(path), "section": title})

    print(f"[B] 按小节切 → {len(texts)} 块（平均 {sum(len(t) for t in texts)//len(texts)} 字符）")
    vecs = embed_batch(texts, batch_size=10, delay=0.12, max_retry=3, verbose=True)
    col.add(ids=[f"s{i:04d}" for i in range(len(texts))],
            documents=texts, metadatas=metas, embeddings=vecs)
    print(f"[B] 入库完成 count = {col.count()}")
    return col


def evaluate(col, tag, query_vecs):
    from embed_batch import embed_batch  # noqa: F401  (保持依赖显式)

    rows = []
    for (num, q, key, src), qv in zip(CASES, query_vecs):
        res = col.query(query_embeddings=[qv], n_results=TOP_K)
        docs = res["documents"][0]
        hit1 = key in docs[0]
        hit3 = any(key in d for d in docs)
        rows.append({"num": num, "q": q, "key": key, "src": src,
                     "hit1": hit1, "hit3": hit3, "top1": docs[0]})
    m1 = sum(r["hit1"] for r in rows)
    m3 = sum(r["hit3"] for r in rows)
    print(f"\n【策略 {tag}】hit@1 = {m1}/{len(rows)}   hit@3 = {m3}/{len(rows)}")
    for r in rows:
        mark = "✅" if r["hit1"] else ("🔶" if r["hit3"] else "❌")
        print(f"  {mark} {r['num']:>2} {r['q']}")
        print(f"       期望含：{r['key']}")
        print(f"       Top-1 ：{r['top1'][:60].replace(chr(10), ' / ')}...")
    return m1, m3, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="只校验短语，不调 API")
    ap.add_argument("--rebuild-b", action="store_true", help="强制重建 B 索引（默认复用）")
    args = ap.parse_args()

    corpus = load_corpus()

    if args.validate:
        ok = validate_cases(corpus)
        sys.exit(0 if ok else 1)

    # 跑之前先挡住未填的题 —— 不让「None 短语」静默通过
    unfilled = [c[0] for c in CASES if c[2] is None]
    if unfilled:
        print(f"❌ 有 {len(unfilled)} 题短语未填：{unfilled}")
        print("   → 先跑 `--validate` 补完，再跑本脚本（否则这些题会全部假失败）")
        sys.exit(2)

    ok = validate_cases(corpus)
    if not ok:
        print("❌ 校验没过（有判据错的短语）→ 先改判据再跑")
        sys.exit(2)

    print("\n" + "=" * 74)
    print("切块策略 A/B · 20 题")
    print("=" * 74)

    client = chromadb.PersistentClient(path=PERSIST_DIR)
    col_a = client.get_collection(COLLECTION_A)
    print("\n【索引体量对比】")
    sa = collection_stats(col_a, "A 固定长度 500/50")
    print_stats(sa)
    if args.rebuild_b:
        col_b = build_section_index()
    else:
        try:
            col_b = client.get_collection(COLLECTION_B)
            print(f"[B] 复用已存在的 {COLLECTION_B}（要重建加 --rebuild-b）")
        except Exception:
            print(f"[B] {COLLECTION_B} 不存在 → 新建")
            col_b = build_section_index()
    sb = collection_stats(col_b, "B 按小节切")
    print_stats(sb)

    # 20 个问题一次向量化（2 批）—— 比每题单独调省钱
    from embed_batch import embed_batch
    print(f"\n[embed] 20 个问题向量化中（{TOP_K} 路检索）...")
    t0 = time.time()
    qvecs = embed_batch([c[1] for c in CASES], batch_size=10, delay=0.12,
                        max_retry=3, verbose=True)
    print(f"[embed] 完成，耗时 {time.time()-t0:.1f}s → 本次成本 = "
          f"{len(CASES)} 次 query-embed（入库侧 0 次，索引是复用的）")

    a1, a3, rows_a = evaluate(col_a, "A 固定长度 500/50", qvecs)
    b1, b3, rows_b = evaluate(col_b, "B 按小节切", qvecs)

    # ── 四列对照表 ──
    lines = ["Week 7 · 切块策略 A/B（20 题）", "=" * 60, ""]
    lines.append("【索引体量 / 混杂块占比 —— 这就是 Q2「代价是什么」的答案】")
    for s in (sa, sb):
        lines.append(f"  {s['tag']:<18} 块数 {s['chunks']:>4} ｜ 平均 {s['avg_len']:>4} 字"
                     f" ｜ 混杂块 {s['mixed']:>4} ({s['mixed_pct']}%)"
                     f" ｜ 无标题块 {s['no_head']:>3} ({s['no_head_pct']}%)")
    lines.append("")
    lines.append(f"  命中率   A : hit@1 {a1}/20   hit@3 {a3}/20")
    lines.append(f"           B : hit@1 {b1}/20   hit@3 {b3}/20")
    lines.append("")
    lines.append("【逐题对照】")
    lines.append(f"{'#':>3} {'提问':<22} {'A':^3} {'B':^3}  期望含")
    for ra, rb in zip(rows_a, rows_b):
        lines.append(f"{ra['num']:>3} {ra['q']:<22} "
                     f"{'✅' if ra['hit1'] else ('🔶' if ra['hit3'] else '❌'):^3} "
                     f"{'✅' if rb['hit1'] else ('🔶' if rb['hit3'] else '❌'):^3}  「{ra['key']}」")
    lines.append("")
    lines.append("【只看 hit@1，是不是两条策略差不多？→ 再看混杂块占比那一列。】")
    out = os.path.join(HERE, "chunking_ab_20_result.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(os.path.join(HERE, "chunking_ab_20_result.json"), "w", encoding="utf-8") as f:
        json.dump({"stats": [sa, sb], "A": {"hit1": a1, "hit3": a3, "rows": rows_a},
                   "B": {"hit1": b1, "hit3": b3, "rows": rows_b}},
                  f, ensure_ascii=False, indent=2)
    print("\n" + "\n".join(lines))
    print(f"\n→ 已落盘 {out}")


if __name__ == "__main__":
    main()
