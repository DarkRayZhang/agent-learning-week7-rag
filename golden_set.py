# -*- coding: utf-8 -*-
"""
Week 7 · 周三 ①：从语料反推 golden set（30 条）
================================================

【为什么"反推"】
教训（09-20 记录）：W6 那 30 条用例的失败根因是「**先想问题 → 再回头对语料**」，
结果 8 条判据指向语料里**根本不存在**的内容 —— 那是**判据错，不是系统错**。
本版改成**反推**：**先定语料里的知识点（keywords）→ 自动找含它的文档（relevant）→ 再配问题**。
这样**分母天然存在**，判据不可能造假。

【跑法】在 week7/ 目录下，用 week5 的 venv：
    ..\\week5\\.venv\\Scripts\\python.exe golden_set.py

【产出】week7/golden_set.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.normpath(os.path.join(HERE, "..", "week5", "docs"))
OUT_PATH = os.path.join(HERE, "golden_set.json")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ══════════════════════════════════════════════════════════════════════
#  30 条「问题 + keywords」—— **keywords 已从语料原样摘出，你只管找 relevant**
#  ── 格式：(题号, 提问, [关键词...], 类别)
#  ── keywords 是**原样子串**，去 week5/docs/ 里能原样找到（不信可以 grep 验）
# ══════════════════════════════════════════════════════════════════════
CASES = [
    # ── 正常题 20 条：库里**有**答案 ──────────────────────────────────
    ( 1, "周报什么时候交",         ["每周五 17:00 前提交", "交周报"],              "正常"),
    ( 2, "会议纪要多久发出来",     ["会议纪要 24 小时内发出"],                    "正常"),
    ( 3, "代码评审会什么时候开",   ["每周三 15:00"],                             "正常"),
    ( 4, "发版前必须确认什么",     ["回滚方案和影响范围"],                        "正常"),
    ( 5, "灰度怎么放量",           ["先放 1% 流量"],                             "正常"),
    ( 6, "事故复盘要产出什么",     ["时间线、根因、可落地的改进项及负责人"],       "正常"),
    ( 7, "变更评审有什么底线",     ["改的人不能审自己的变更"],                    "正常"),
    ( 8, "监控告警的时效要求",     ["异常 5 分钟内要触发告警"],                   "正常"),
    ( 9, "健康检查接口为什么必须加", ["会把还没起来的实例也算进负载"],             "正常"),
    (10, "什么情况该用警告级别",   ["可以自动重试或降级恢复"],                    "正常"),
    (11, "数据库备份保留多久",     ["保留周期 30 天"],                           "正常"),
    (12, "幂等键放在哪",           ["幂等键放在请求头里"],                        "正常"),
    (13, "缓存穿透怎么处理",       ["查不到的数据也要缓存一个空值"],              "正常"),
    (14, "睡眠目标是什么",         ["目标 23:30 前躺下"],                        "正常"),
    (15, "久坐怎么缓解",           ["每工作 50 分钟起来活动 5 分钟"],             "正常"),
    (16, "护照有效期要求",         ["护照有效期必须剩 6 个月以上"],              "正常"),
    (17, "酒店怎么选",             ["选地铁站 800 米以内的"],                    "正常"),
    (18, "述职材料怎么写",         ["要拿数据说话"],                             "正常"),
    (19, "空调滤网多久洗一次",     ["空调滤网每月洗一次"],                       "正常"),
    (20, "生鲜什么时候买",         ["每周六上午去菜市场"],                       "正常"),

    # ── 多跳题 5 条：答案**散在 ≥2 个文档**里 → recall@k 才有区分度 ★ ──
    #    （单文档题 recall@k 容易"0 或 1"跳变；多文档题才能看出 k 的边际收益）
    (21, "感冒了怎么办、平时怎么防", ["常备退烧、止痛、肠胃药", "抗生素必须凭处方购买"], "多跳"),
    (22, "眼睛不舒服怎么办",       ["遵守 20-20-20 规则", "不要长期用去红血丝的眼药水"], "多跳"),
    (23, "出差有哪些注意事项",     ["发票必须当月交", "托运行李里不要放锂电池和充电宝"], "多跳"),
    (24, "怎么写好一次变更",       ["每次生产变更都要有人复核", "紧急变更可以先上线后补单"], "多跳"),
    (25, "跑步怎么保护膝盖",       ["膝盖有不适就换成游泳或骑车", "跑鞋跑到 600 公里左右就该换"], "多跳"),

    # ── 拒答题 5 条：库里**故意没有** → relevant 应为 [] ★ ────────────
    #    （这一格才是"升级"的精髓：把「拒答」也变成**可算的基线**）
    (26, "量子纠缠的原理是什么",   ["量子纠缠", "波函数坍缩"],                    "拒答"),
    (27, "怎么申请公积金贷款",     ["公积金贷款", "首付比例"],                    "拒答"),
    (28, "公司组织架构是什么样",   ["组织架构", "汇报关系"],                      "拒答"),
    (29, "世界杯冠军是哪支球队",   ["世界杯冠军", "决赛比分"],                    "拒答"),
    (30, "怎么给孩子做辅食",       ["辅食食谱", "辅食机"],                        "拒答"),
]


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 1：从语料反推 golden set（你来写，约 8~12 行）
# ══════════════════════════════════════════════════════════════════════
def build_golden_set(cases, docs_dir):
    """从语料反推：每个问题的**相关文档列表**（= golden 集的全部内容）。

    入参：
        cases    —— 上面的 CASES，[(num, query, keywords, category), ...]
        docs_dir —— week5/docs/ 的路径

    出参（list[dict]，**顺序与 cases 一致**）：
        [{"num": 1, "query": "周报什么时候交", "keywords": ["每周五 17:00 前提交", "交周报"],
          "category": "正常", "relevant": ["doc_007.md", "doc_033.md"], "n_relevant": 2}, ...]

    判据（**验收就按这 5 条数**）：
      ① relevant 必须非空 —— 空即判据错（W6 那 8 条就是这毛病）→ **直接 raise**
      ② relevant 的判定 = 文档正文里出现该题**任意一个** keyword（`any`，**不是 `all`**）
      ③ n_relevant == len(relevant) —— **分母单独存一份**（每次现算迟早会算错）
      ④ category == "拒答" 时 relevant 允许为 []，**且必须为空**（= 库里确实没有）
      ⑤ 输出顺序与 cases 一致（**别用 set 导致乱序**，乱序了和题号就对不上）

    提示（4 步）：
      1. 先看数据：`ls ../week5/docs/ | head` / `head -30 ../week5/docs/doc_001.md`
      2. 读全部文档 → {文件名: 正文}：`for name in sorted(os.listdir(docs_dir)) if name.endswith(".md")`
      3. 每题一遍：`relevant = [name for name, body in docs.items()
                                 if any(kw in body for kw in keywords)]`
      4. 按 category 分岔：正常/多跳 → 空 relevant 就 raise；拒答 → 空 relevant 才正常
    """

    docs ={}
    for name in sorted(os.listdir(docs_dir)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(docs_dir,name),encoding="utf-8") as f:
            docs[name] = f.read()

    golden =[]
    for num, query, keywords,category in cases:
        relevant = [name for name, body in docs.items()
                    if any(kw in body for kw in keywords)]
        if not relevant and category != "拒答":      #<- 没有关联性然后不是拒答的话那么直接报错
            raise ValueError(f"#{num} 「{query}」判据错：语料里找不到任何关键词 {keywords}")
        if relevant and category == "拒答":         #<- 有关联性然后是拒答的话那么直接报错
            raise ValueError(f"#{num} 「{query}」标注了拒答：语料里缺命中了 {relevant}")
        golden.append({"num": num,"query": query,
                       "keywords": keywords,"category": category,
                       "relevant": relevant,
                       "n_relevant": len(relevant),})  #<- 分母单独存一份
    return golden


# ══════════════════════════════════════════════════════════════════════
#  ★ 函数 2：落盘（你来写，3 行）
# ══════════════════════════════════════════════════════════════════════
def save_golden_set(path, golden):
    """写 JSON 到 path。

    判据：
      ① `ensure_ascii=False` —— 不然中文全是 \\uXXXX，你自己都没法 review
      ② `indent=2` —— 方便直接打开看/手改
      ③ **返回写出条数**（方便 main 打印）
    """
    with open(path,"w",encoding="utf-8") as f:
        json.dump(golden,f,ensure_ascii=False,indent=2)
    return len(golden)


# ══════════════════════════════════════════════════════════════════════
#  main —— 我写好了，你**别改**（它是验收的一部分）
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 74)
    print("golden set 构建（从语料反推，0 次 API）")
    print("=" * 74)
    print(f"语料：{DOCS_DIR}\n")

    golden = build_golden_set(CASES, DOCS_DIR)

    # ── 自检（我写死，不看你的实现）──
    print("[自检] ① 条数：", len(golden), "==", len(CASES),
          "✅" if len(golden) == len(CASES) else "❌ 条数对不上")
    print("[自检] ⑤ 顺序：", "✅" if [g["num"] for g in golden] == [c[0] for c in CASES]
          else "❌ 题号顺序乱了（是不是用了 set？）")

    empty_normal = [g["num"] for g in golden if g["category"] != "拒答" and not g["relevant"]]
    print("[自检] ① 正常/多跳题 relevant 非空：",
          "✅" if not empty_normal else f"❌ 这几题空了：{empty_normal}")

    nonempty_refuse = [g["num"] for g in golden if g["category"] == "拒答" and g["relevant"]]
    print("[自检] ④ 拒答题 relevant 为空：",
          "✅" if not nonempty_refuse else f"⚠️ 这几题拒答题竟然命中了：{nonempty_refuse}")

    bad_denom = [g["num"] for g in golden if g.get("n_relevant") != len(g["relevant"])]
    print("[自检] ③ n_relevant 与 relevant 一致：",
          "✅" if not bad_denom else f"❌ 这几题对不上：{bad_denom}")

    # ── 分布读数（这就是"分母"长什么样）──
    print("\n[读数] 每题相关文档数（分母）分布：")
    for g in golden:
        bar = "█" * g["n_relevant"]
        print(f"  #{g['num']:>2} [{g['category']}] n={g['n_relevant']:>2} {bar:<10} "
              f"{g['relevant'][:3]}{' ...' if len(g['relevant']) > 3 else ''}")

    n = save_golden_set(OUT_PATH, golden)
    print(f"\n→ 已落盘 {OUT_PATH}（{n} 条）")

    # ── 基线预判：分母的平均值决定了 recall 的"分辨率" ──
    normals = [g for g in golden if g["category"] != "拒答"]
    if normals:
        avg = sum(g["n_relevant"] for g in normals) / len(normals)
        print(f"[读数] 非拒答题平均分母 = {avg:.1f} 篇（< 2 的题 recall 只有 0/0.5/1 三档，"
              f"分辨率低）")
    print(f"[读数] 拒答题 {sum(1 for g in golden if g['category'] == '拒答')} 条"
          f" → recall 里**不参与平均**（返回 None），单独看它们的命中数（越少越好）")


if __name__ == "__main__":
    main()
