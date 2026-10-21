# -*- coding: utf-8 -*-
"""繁简变体 —— 规则跟 CathayHub（CathaySearch / CathayViewer）保持一致。

用户口径：「繁简通搜参考 CathayHub」。CathayHub 里那套核心在
`query_expand.py`（OpenCC 四个配置 t2s / s2t / s2tw / s2hk 轮着套，
没装 OpenCC 时退回 zhconv 的 zh-cn / zh-tw），本模块只把
**字符串级**的转换与「变体铺开」照抄过来，不碰任何文件、
不认任何界面 —— 跟那边转出来的字形必须一模一样。

一个简体字常对应不止一个繁体字形（启 → 啓 / 啟），所以不是
"简↔繁"两条路，而是四个方向反复套到不再冒出新词为止 ——
无论从简体还是繁体出发，得到的都是同一组字形。
"""
import threading

_CC = {}
_CC_LOCK = threading.Lock()

MAX_VARIANTS = 32     # 一个检索词最多带这么多个字形一起去搜（防表达式撑爆）

# 四个 OpenCC 配置轮着套：少认一个字形就少一半存货
_CONV_CFGS = ('t2s', 's2t', 's2tw', 's2hk')


def _cc(cfg):
    if cfg not in _CC:
        with _CC_LOCK:
            if cfg not in _CC:
                import opencc
                _CC[cfg] = opencc.OpenCC(cfg)
    return _CC[cfg]


def convert_text(text, act):
    """act: 't2s'（繁→简）/ 's2t'（简→繁）/ 's2tw' / 's2hk'。优先 OpenCC，退回 zhconv。"""
    text = text or ''
    try:
        return _cc(act).convert(text)
    except Exception:
        try:
            import zhconv
            return zhconv.convert(text, 'zh-cn' if act == 't2s' else 'zh-tw')
        except Exception:
            return text


def variants_of(word):
    """一个词的全部繁/简变体，**不含自身**；繁简同形返回空表。

    做法：四个方向的转换反复套到不再冒出新词为止（最多三轮）。
    好处是**对称** —— 无论从简体还是繁体出发，得到的都是同一组字形。
    """
    w = str(word or '').strip()
    if not w:
        return []
    out = []
    src = [w]
    for _ in range(3):
        grown = False
        for x in src:
            for cfg in _CONV_CFGS:
                v = convert_text(x, cfg)
                v = (v or '').strip()
                if v and v != w and v not in out:
                    out.append(v)
                    grown = True
        if not grown:
            break
        src = [x for x in [w] + out]
    return out


# ═══════════════════════ 逐字铺开（一字多繁）═══════════════════════
# 整串转出来只给一种写法，可有些简体字有好几个繁体，各自都在用：
#   「汇编」整串转 → 彙編，可书库里有成排的「…史料匯編」，
#   「头发」整串转 → 頭髮，可「理发」那条写的是理髮（对）、但也有「發」的错写。
# 只按整串转，打简体就搜不到写另一个字形的那些书。所以再补一轮：
# 把每个有多个繁体写法的字，各换一种，组合出残余写法。
# 字表直接读 opencc 自带的 STCharacters.txt（单字行），只取每个简体字的
# **第一个**候选与前 4 个候选，组合数封顶 MAX_CHAR_COMBOS，防止表达式撑爆。

_ST = {}
_ST_LOADED = False
_ST_LOCK = threading.Lock()

MAX_CHAR_COMBOS = 24      # 逐字铺开最多再补这么多个写法


def _st_map():
    """{简体单字: [繁体候选...]}（只含候选 ≥2 个的字；读不到给空表）"""
    global _ST, _ST_LOADED
    if _ST_LOADED:
        return _ST
    with _ST_LOCK:
        if _ST_LOADED:
            return _ST
        d = {}
        try:
            import opencc, os
            root = os.path.dirname(os.path.abspath(opencc.__file__))
            path = os.path.join(root, 'dictionary', 'STCharacters.txt')
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if not line or line.startswith('#'):
                        continue
                    k, _, v = line.partition('\t')
                    if len(k) != 1:
                        continue
                    cands = [x.split()[0] for x in v.split(' ') if x]
                    cands = [c for c in cands if c != k]
                    if len(cands) >= 2:
                        d[k] = cands[:4]
        except Exception:
            d = {}
        _ST, _ST_LOADED = d, True
    return _ST


def _pairs(word):
    """[(简/原字, [它的各个繁体写法])]，只取「一字多繁」且当前写法就是其中之一的字。

    例：'…史料彙編' → [('汇', ['匯','彙']), ('编', ['編'])] 里只留 '汇'
    （'编' 只有一个写法，不算）。'…史料匯編' 同样只留 '汇'。
    这样就能从**已经转好的整句**出发，只把「汇」换成「匯」或「彙」，
    得到 …史料匯編 / …史料彙編，而不是一堆半简半繁的混合体。
    """
    w = str(word or '')
    if not w:
        return []
    st = _st_map()
    out = []
    for pos, ch in enumerate(w):
        if ch in st:                       # 字本身是简体、有多个繁体写法
            out.append((pos, ch, st[ch]))
            continue
        for simp, cands in st.items():     # 字本身是某个繁体写法
            if ch in cands:
                out.append((pos, simp, cands))
                break
    return out


def char_forms(word, limit=None):
    """把「一字多繁」的字各换一种，组合出残余写法（不含自身）。

    「汇」有两个繁体（匯 / 彙），整串转换只会给一种，可书库里两种都在用：
    打「…史料汇编」应当同时搜到「…史料彙編」和「…史料匯編」。
    本函数从已转换好的整句出发，把这类字逐个换掉，组合出其余写法。

    只接受「整句同一字形体系」的组合：整句过一遍 t2s 会变 = 繁体句，
    这时把「汇」换成 匯 或 彙 都合法；不变 = 简体句，换一处就得到
    「…史料匯编」这种半简半繁的废组合，直接不生成（白占名额还搜不到东西）。
    """
    w = str(word or '').strip()
    if not w:
        return []
    limit = MAX_CHAR_COMBOS if limit is None else limit
    pairs = _pairs(w)
    if not pairs:
        return []
    # 判断整句是繁体还是简体：整句过一遍 t2s —— 变了就是繁体句，可以放心换
    # （匯/彙 都成）；没变就是简体句，换一处只会得到半简半繁的废写法。
    if convert_text(w, 't2s') == w:
        return []
    out = []

    def walk(i, chars):
        if len(out) >= limit:
            return
        if i == len(pairs):
            s = ''.join(chars)
            if s != w and s not in out:
                out.append(s)
            return
        pos, simp, cands = pairs[i]
        for c in cands:
            chars[pos] = c
            walk(i + 1, chars)
            if len(out) >= limit:
                break
        chars[pos] = w[pos]

    walk(0, list(w))
    return out


def all_variants(word, limit=MAX_VARIANTS):
    """整串铺开 + 逐字铺开，合起来去重（不含自身）。这是检索真正用的那一份。

    对每个已经铺开的写法再逐字补一遍（简体出发 → 繁体句 → 换掉「汇」得匯編），
    最多三轮直到不再冒新词，保证各种「一字多繁」的组合都被覆盖到。
    """
    w = str(word or '').strip()
    if not w:
        return []
    out = list(variants_of(w))
    src = [w] + out
    for _ in range(3):
        grown = False
        for base in list(src):
            for v in char_forms(base):
                if v and v != w and v not in out:
                    out.append(v)
                    grown = True
                    if len(out) >= limit:
                        return out
        if not grown:
            break
        src = [w] + out
    return out


def selftest():
    """自检：转换可用性 + 对称性 + 一字多繁（汇→匯/彙）+ 已知例子。"""
    lines = []
    try:
        import opencc                       # noqa: F401
        lines.append("engine=opencc")
    except Exception:
        try:
            import zhconv                   # noqa: F401
            lines.append("engine=zhconv")
        except Exception:
            lines.append("engine=none（繁简通搜将自动等于原样搜索）")
    a = variants_of("梁启超")
    b = variants_of("梁啟超")
    if "梁啓超" in a:
        lines.append("t2s样例=梁啓超 OK")
    else:
        lines.append("t2s样例=FAIL %r" % (a,))
    lines.append("对称=%s（简出%d个 / 繁出%d个）"
                 % ("OK" if set(a) == set(b) or not (a or b) else "WARN",
                    len(a), len(b)))
    # 一字多繁：汇编 → 彙編（整串转）+ 匯編（逐字铺开）
    v = all_variants("中国古代汉族与少数民族关系史料汇编")
    want = ["彙編", "匯編"]           # 只要求两种都在，不锁死顺序
    ok_hui = all(any(w in x for x in v) for w in want)
    lines.append("一字多繁=汇→匯/彙 %s（%d 个写法：%s）"
                 % ("OK" if ok_hui else "FAIL", len(v),
                    "、".join(x[-2:] for x in v)))
    lines.append("纯数字=%r（应为空）" % (all_variants("14296873"),))
    lines.append("字表=%d 个多写法简体字" % len(_st_map()))
    return "\n".join(lines)


if __name__ == "__main__":
    print(selftest())
