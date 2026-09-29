# W7 周三 · 任务卡：golden set + recall@5 基线（09-27 晚 21:10–22:40）

> **今晚只做这一件**（1.5h）：把「评测」这件事**从"感觉更准了"变成"有个数"**。
> Java 主线骨架（pom + ChatClient + 工具方法）→ **顺延 09-28 晚**（原排本来就是 09-27，但今天只剩 1.5h，装不下两条线）。

---

## 一、先想清三个问题（20min · 只读不问人）

### Q1：golden set 是什么？为什么要它？

**现状**：你手上的两个评测口径都**不测召回**——
| 现有口径 | 测什么 | 缺什么 |
|---|---|---|
| `chunking_ab.py` 的 20 题 | Top-K 里**有没有**关键短语（hit@K） | 只在 20 题上、**没有分母概念**、不测"答案一共散落在几篇" |
| `week6/test_cases.py` 的 30 条 | 端到端**通过 / 拒答**（含生成） | 把「检索失败」和「生成失败」搅在一起，**定位不了病** |

**golden set** = 给每个问题配上**标准答案集**（这题的正确内容都在哪些文档里），然后算：
> 「**该被召回的文档里，我实际召回了几个**」

一句话记忆：**hit@K 问"有没有"，recall@K 问"有几个 / 共几个"**。

### Q2：recall@k 的分子分母各是什么？（**这是自检题**）

```
              Top-k 结果中，命中 golden 集的文档数
recall@k = ─────────────────────────────────────────
                 golden 集中该题的全部文档数
```

- **分母**：golden 集里、这题的**全部**相关文档数（`|relevant|`）—— **先于检索就定好的常数**
- **分子**：Top-k 里，**与 golden 集有交集**的文档数（或：命中的相关文档数，取交集去重）
- **关键点①**：分母**不能是 K**。若分母写 5，那 recall@5 永远等于"命中数/5"，跟"这题一共该召回几篇"无关 → **那是 precision 的变体，不是 recall**
- **关键点②**：recall@k **一定 ≥ hit@k 的强度**（hit@k 只关心"至少中一个"，recall 关心"中了一半还是全部"）
- **关键点③**：k 越大 recall 越高（单调不减）→ **报 recall 必须带 k**，裸报"recall 92%"= 没说

### Q3：为什么 W6 那 30 条要「升级」而不是「重写」？

因为它们的失败根因已经查明（09-20 记录的）：
> **题是"先想问题、再回头对语料"造的** → 8 条判据指向语料里**根本不存在**的内容。

**升级 = 反过来造**：**先选语料里的一个知识点 → 再写问题 → 把"含这个知识点的文档"作为期望命中集**。
这样** denominators 天然存在**，判据不可能造假。

---

## 二、今晚要产出的东西

| # | 文件 | 谁写 | 判据 |
|:--:|---|---|---|
| 1 | `week7/golden_set.py` | **我搭骨架** | 签名 + docstring + 自检 + 4 步提示，**函数体你写** |
| 2 | `week7/golden_set.json` | 脚本生成 | 30 条，每条：`query` / `keywords` / `relevant`（文档名列表）/ `category` |
| 3 | `week7/eval_recall.py` | **我搭骨架** | 只测**检索层**（不调 LLM），跑出 recall@1/@3/@5 |
| 4 | `notes.md` 周三节第 1、2 格 | **你手写** | 填进去 + 基线数字 |

### `golden_set.py` 要你写的两个函数

```python
def build_golden_set(cases, docs_dir):
    """从语料反推 golden set。
    入参：
        cases    —— [(num, query, keywords, category), ...] 我给你的 30 条"问题+关键词"
        docs_dir —— week5/docs/ 路径
    出参：
        [{"num":1, "query":"...", "keywords":[...], "relevant":["doc_007.md", ...],
          "n_relevant":2, "category":"正常"}, ...]

    判据（5 条）：
      ① relevant 必须非空 —— 空 = 判据错（W6 那 8 条就是这毛病），**直接抛异常**
      ② relevant 的判定 = 文档正文里出现该题**任意一个** keyword（原样子串）
      ③ n_relevant == len(relevant)（**分母**，单独存一份，别每次现算）
      ④ 每条都要打 category 标签（正常/拒答/多跳），拒答题 relevant = []
      ⑤ 输出顺序与 cases 一致（别用 set 导致乱序）
    """


def save_golden_set(path, golden):
    """落盘 JSON（ensure_ascii=False, indent=2）—— 方便你直接打开看。"""
```

**提示（4 步）**：
1. **先看数据长什么样**：`ls ../week5/docs/ | head`，再 `head -30 ../week5/docs/doc_001.md`
2. **"相关"怎么判**：读全部文档到 `{文件名: 正文}`，对每题的 keyword 逐个 `kw in body`
3. **每题一个循环**：`relevant = [name for name, body in docs.items() if any(kw in body for kw in kws)]`
4. **拒答题特殊处理**：库里**故意**没有 → `relevant=[]` 是**正常的**，但要能从 category 区分（不能和"判据错"混）

### `eval_recall.py` 要你写的两个函数

```python
def recall_at_k(retrieved_ids, relevant_ids, k):
    """算一题的 recall@k。
    retrieved_ids —— 检索返回的**有序** id 列表（Top-N，N ≥ k）
    relevant_ids  —— golden 集里该题的相关文档（文件名列表，**无序**，可能为空）
    返回 float：
      · relevant_ids 为空（拒答题）→ 返回 None（**不参与平均**，别当 0 拉低基线）
      · 否则 = |Top-k ∩ relevant| / |relevant|
    """


def eval_one_query(col, qvec, golden_item, k_list=(1, 3, 5)):
    """单题评测：拿 Top-max(k_list) 的**文档名**，对每个 k 算 recall。
    返回 {"num":..., "query":..., "per_k": {1: 0.0, 3: 0.5, 5: 1.0}, "top_names":[...]}

    ⚠️ 关键坑：Chroma 返回的 `ids` 和 `metadatas[source]` **不是一回事** ——
       路径 A（推荐）：`include=["metadatas"]` → 取 `m["source"]`（**和 golden 同一命名空间**）
       路径 B：用 `ids` → 但 golden 里存的是文件名 → **两套 id 对不上，算出来全是 0**
       → 先跑一题把两边打出来对一眼，确认对齐再跑全量。
    """
```

**提示（4 步）**：
1. 索引复用 `week5_docs`（200 块），**A 组**就好——今天不比 A/B，只求基线
2. 向量化 30 个问题 → **1 次 API**（可复用 `week7/query_vec_cache.json`？**不，那是 20 题的**，对不上 → 老老实实新 embed 一次，成本 ≈0）
3. 检索 **n_results=5**
4. **先打印一题的两边对不对齐**，再跑全量 —— 这就是你月考题里写的"跑通 ≠ 写对"的同款闸门

---

## 三、验收（你在跑完后的自检）

- [ ] `golden_set.json` 里 **30 条全有非空 relevant 或明确标拒答**，没有空 relevant 的"正常"题
- [ ] 能口述 **recall@k 分母分子**（不看笔记），且能说清"分母为什么不是 k"
- [ ] `eval_recall.py` 跑出 **recall@1 / @3 / @5** 三个数，落盘 `eval_recall_result.txt`
- [ ] 基线记进 `notes.md` 周三节第 2 格：`recall@5 = __%`
- [ ] **能解释为什么 recall@5 ≥ recall@1**（单调性）

---

## 四、⚠️ 预判你会踩的坑（对答案用，先别看）

<details>
<summary>点开看（先自己写，卡住 5min 以上再看）</summary>

1. **分母写成 k** —— 最经典。`recall@5 = 命中数 / 5` ✗ → 那是 precision
2. **golden 空 relevant 被当 0** —— 拒答题拉低基线 ✗
3. **id 空间不对齐** —— Chroma 的 `ids`（`doc_007.md` 里的块 id）vs 文件名 ✗
4. **`any` 写成 `all`** —— 要求关键词全中，分母会缩到很小 ✗
5. **A 组混杂块 69.5%** —— 一个块跨 2~3 个小节 → 命中"文件名"算命中，但**块本身可能是混杂的** → 这正是 recall 会**高估**的地方（留着，W9 上 Langfuse 再治）

</details>

---

## 五、顺延说明（记账，不丢）

| 项 | 原排 | 新排 | 理由 |
|---|---|---|---|
| Spring AI 骨架（pom + ChatClient + 工具方法） | 09-27 日 | **09-28 一晚** | 今晚只剩 1.5h；且 Java 骨架要拉依赖，网络不确定性大，不适合赶末班车 |
| Java 主线补完（接备忘录检索 + 4 条验收） | 09-28 晚 | 09-29 晚 | 连带顺延一格 |
| Java README + push | 09-29 晚 | 09-30 晚（与 W7 收口合并） | 连带顺延一格 |
| ⚠️ 风险 | — | — | **09-28~30 三晚要装完整个 Java 双实现**，原计划就标注"偏紧"，现在更紧 → **09-29/09-30 若加班，Java 主线会被压** → 备选：把「备忘录检索」降级为"接口占位 + 说明"，保骨架跑通这条硬线 |

</details>
