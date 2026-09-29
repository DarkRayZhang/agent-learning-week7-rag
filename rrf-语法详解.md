# RRF / rerank 代码详解 + API 词典（Java 对照）

> 用途：给 `week7/hybrid_rerank.py` 里那两个**留空的函数**当参照。
> ⚠️ **参照 ≠ 复制** —— 照着敲一遍，敲完自己跑，读数才是你的。

---

## 一、`rrf_fuse` 逐行

### 第 1 行 `rank_vec = {doc_id: r for r, doc_id in enumerate(vec_ids, 1)}`

这行塞了三个语法点，拆开看：

**① `enumerate(vec_ids, 1)`**
- 返回一个**枚举器**：每次吐出 `(序号, 元素)`
- **第二个参数是起点**（Python 默认是 `0` —— 这里必须写 `1`，因为 RRF 的 rank 从 1 开始）
- Java 对应：
  ```java
  for (int r = 1; r <= vecIds.size(); r++) { String id = vecIds.get(r - 1); ... }
  ```

**② `for r, doc_id in ...` —— 元组解包（unpacking）**
- 枚举器每次给一个 `(1, "c0000")`，这行直接把它拆成两个变量
- Java 没有对应写法（Java 得用 `Map.Entry` 或 `int[]` 绕）

**③ `{key: value for ...}` —— 字典推导（dict comprehension）**

它等价于这三行：
```python
rank_vec = {}
for r, doc_id in enumerate(vec_ids, 1):
    rank_vec[doc_id] = r
```
- Java 对应：`Map<String,Integer> m = new HashMap<>(); for (...) m.put(id, r);`

---

### 第 2 行 `for doc_id in set(vec_ids) | set(bm25_ids):`

**① `set(xs)`** —— 把列表转成**集合**：去重 + 可做集合运算
- ⚠️ **集合是无序的**（底层哈希表）—— 这里无所谓（后面要按分数重排）
- Java 对应：`new HashSet<>(list)`

**② `|`** —— **并集运算符**（等价 `set(a).union(set(b))`）
- Java 对应：`Set<String> s = new HashSet<>(a); s.addAll(b);`

**③ `for doc_id in ...`** —— 直接迭代集合元素，不需要下标
- Java 对应：`for (String id : s)`

---

### 第 3 段：累加循环

```python
        total = 0.0
        r = rank_vec.get(doc_id)
        if r is not None:
            total += 1.0 / (k + r)
```

**① `total = 0.0`** —— 显式写浮点零，表意清楚。（Python 的 `0 + 1.0/x` 也会自动变 float，但别依赖这个）

**② `.get(doc_id)` —— 字典的 get，这是整段的核心**
- key 存在 → 返回值
- **key 不存在 → 返回 `None`（不抛异常！）**
- Java 对应：`map.get(k)` → **`null`** ← ⭐ **这是少见的 Java/Python 行为完全一致的地方**
- 对照：**中括号**写法 `rank_vec[doc_id]` 找不到会**抛 `KeyError`** —— 所以我们用 `.get`
- 为什么用 `.get` 而不是 `if doc_id in rank_vec:` + `[]`：一行搞定，且只做一次哈希查找

**③ `if r is not None:`**
- Python 里判断 None 的**规范写法是 `is None` / `is not None`**（PEP 8），不是 `!= None`
- 原因：`is` 比的是**对象身份**（同一块内存），`==` 比的是**值**（会调用 `__eq__`）；对 `None` 应该比身份
- Java 对应：`if (r != null)`
- ⚠️ **不判断会怎样**：`1 / (k + None)` → `TypeError`（崩）

**④ `total += 1.0 / (k + r)`**
- ⚠️ **Python 3 的 `/` 永远是浮点除法**：`5 / 2 == 2.5`
- Java 的 `/` **整数相除会截断**：`5 / 2 == 2` ← 这是最容易带错过来的习惯
- Python 的整除要写 `//`（`5 // 2 == 2`）

---

### 最后一行 `return sorted(scores, key=scores.get, reverse=True)`

**① `sorted(xs)`** —— 返回**新的列表**
- 对照：`xs.sort()` 是**原地排序**，而且**返回 None**（写成 `a = xs.sort()` 会得到 `None`，经典坑）

**② `sorted(scores)` 排的是什么？** —— **迭代 dict 得到的是 key**
- 所以 `sorted(scores)` = 对 **id 列表**排序，不是对 `(id, 分数)` 排

**③ `key=scores.get`** —— **把函数当参数传**（Python 的"函数是一等公民"）
- 等价写法：`key=lambda i: scores[i]`
- `scores.get` 是**绑定方法**：它已经"记住"了 `scores` 这个字典
- Java 对应：`Comparator.comparing(scores::get)`（Java 得包一层 `Comparator`）

**④ `reverse=True`** —— 降序
- Java 对应：`.reversed()`

---

## 二、`rerank_rule` 逐行

### `q_set = set(tokenize_zh(query))`
- `tokenize_zh(query)` 返回的是一个 **list**（字符 bigram，**可能重复**，比如"什么"出现两次）
- `set(...)` 去重 → **集合**。为什么必须转集合：**要支持 `&` 交集**，而且去重后交集大小 = "**不同** bigram 的命中数"（不是出现次数）

### `for rank, doc in enumerate(docs):`
- 这里 `enumerate` **不传第二个参数**，起点是默认的 `0` —— 只拿来做 tie-break，够用

### `hit = len(q_set & set(tokenize_zh(doc)))`
**① `&`** —— **交集**运算符（等价 `q_set.intersection(...)`）
- Java 对应：`Set<String> s = new HashSet<>(a); s.retainAll(b); int n = s.size();`

**② `len(...)`** —— 长度
- ⚠️ **Python 一律用 `len()`**：集合、列表、字符串、字典都它
- Java 三种写法：`.size()`（集合）/ `.length`（数组）/ `.length()`（字符串）

**③ 整个表达式** = "query 里有多少个**不同的** bigram 出现在这个块里"

### `scored.append((hit, -rank, doc))`
**① `.append(x)`** —— 尾部追加（Java `add`）

**② `(hit, -rank, doc)`** —— **元组（tuple）**：不可变、可以混装不同类型
- Java 对应：`record` / `List.of(...)` / 自己写个类

**③ 为什么是 `-rank` 而不是 `rank`** —— 这是这一段唯一的"设计"：
- 后面是**降序**排。命中数相同时，我们希望**原来的向量名次小的排前面**
- `rank=0 → -rank=0`；`rank=1 → -rank=-1`；`rank=2 → -rank=-2`
- 降序：`0 > -1 > -2` → **rank 越小越靠前** ✓
- 如果直接写 `rank`，降序会变成"名次大的排前面"—— 完全反了

### `scored.sort(key=lambda t: (t[0], t[1]), reverse=True)`
**① `.sort()`** —— **原地排序**（⚠️ 返回 `None`，别接）
**② `lambda t: (t[0], t[1])`** —— **lambda 匿名函数**（Java `t -> ...`）
- `t` 是那个三元组；`t[0]` = hit、`t[1]` = -rank
**③ 元组比较是"字典序"**：先比 `t[0]`，**相等才比 `t[1]`** —— 这就是 Python 实现**多级排序**的方式
- Java 对应：`Comparator.comparingInt(...).thenComparingInt(...)`

### `return [t[2] for t in scored]`
- **列表推导**：把每个元组的第 3 个元素（`doc`）取出来组成新列表
- Java 对应：`scored.stream().map(t -> t.get(2)).collect(Collectors.toList())`

---

## 三、API 速查词典

| API | 是什么 | Java 对应 | ⚠️ 坑 |
|---|---|---|---|
| `enumerate(xs, 1)` | 枚举器 → `(序号, 元素)` | 手写 `for` + `get` | **默认起点是 0** |
| `{k: v for ...}` | 字典推导 | 手写 `put` | |
| `set(xs)` | 转集合（去重、**无序**） | `new HashSet<>(xs)` | 无序 |
| `a \| b` | **并集** | `addAll` | |
| `a & b` | **交集** | `retainAll` | |
| `len(x)` | 长度 | `.size() / .length / .length()` | **Python 统一 `len()`** |
| `d.get(k)` | 取值，**缺省 None** | `map.get(k)` → `null` | ⭐ **行为一致** |
| `d[k]` | 取值，**缺省抛 KeyError** | —— | ⚠️ 会抛 |
| `x is None` | 身份比较 | `x == null` | 规范写法 |
| `xs.append(x)` | 追加 | `add` | |
| `xs.sort()` | 原地排序 | `Collections.sort` | ⚠️ **返回 None** |
| `sorted(xs, key=f)` | 返回**新列表** | `stream().sorted` | |
| `lambda x: ...` | 匿名函数 | `x -> ...` | |
| `(a, b, c)` | 元组（不可变） | `record` | |
| `[f(x) for x in xs]` | 列表推导 | `stream().map` | |
| `1.0 / 2` | **浮点除法** | `5/2` 会截断 | ⚠️ **Python3 的 `/` 总是浮点** |

---

## 四、自测（敲完回答，别翻上面）

1. `sorted(scores, key=scores.get, reverse=True)` 里，为什么 `key` 要传 `scores.get` 而**不是** `scores`？
2. `-rank` 那一位，如果改成 `rank`，排序结果会怎么变？
3. `rank_vec.get(doc_id)` 和 `rank_vec[doc_id]` 的区别是什么？
