"""Report strings. English is the default; Chinese is opt-in via --lang zh."""

from __future__ import annotations

STRINGS: dict[str, dict[str, object]] = {
    "en": {
        "title": "{a} vs {b}",
        "meta": "- `{id}` v{version}: {n} items, missing={missing}, validation={validation}, sha256={hash}",
        "complete_pairs": "- complete pairs: **n = {n}**",
        "descriptives": "Descriptives",
        "reliability": "Internal consistency",
        "association": "Association",
        "agreement": "Agreement",
        "agreement_note": (
            "> Pearson correlation describes linear association. ICC(2,1) and "
            "Bland-Altman are auxiliary outputs for scores on a defensible common "
            "metric. Raw scores on different metrics do not establish "
            "interchangeability. Standardizing scores changes the estimand; "
            "it does not establish interchangeability of the original scores."
        ),
        "classification": "Classification agreement",
        "kappa": "kappa = {kappa:.3f}, observed agreement = {agreement:.3f}, n = {n}",
        "skipped_cutoffs": "Skipped: at least one instrument defines no cutoffs.",
        "crosswalk": "Equipercentile crosswalk (mid-percentile / linear quantile)",
        "crosswalk_warning": (
            "> Warning: n < 100; linked scores are unstable. "
            "Report confidence intervals and treat as exploratory."
        ),
        "subscale_corr": "Subscale correlations",
        "methods": "Methods paragraph (draft)",
        "methods_text": (
            "> Scores on the {a} and the {b} were computed with BRIDGE-D "
            "v{version} using each instrument's declared scoring and missing-data "
            "rules. Pearson correlation describes the primary linear association; "
            "Spearman correlation is supplementary. ICC(2,1) and Bland-Altman "
            "limits are auxiliary agreement summaries requiring a defensible "
            "common score metric. Classification agreement used Cohen's kappa "
            "at each instrument's published cutoffs. Cross-scale linking used "
            "mid-percentile ranks and linear target quantile interpolation "
            "with {n_boot} bootstrap resamples (n = {n})."
        ),
        "headers": {
            "scale": "scale",
            "n": "n",
            "mean": "mean",
            "sd": "SD",
            "median": "median",
            "min": "min",
            "max": "max",
            "missing": "missing",
            "alpha": "alpha",
            "pair": "pair",
            "pearson": "Pearson",
            "spearman": "Spearman",
            "mean_diff": "mean diff",
            "sd_diff": "SD diff",
            "loa_lower": "LoA lower",
            "loa_upper": "LoA upper",
            "icc21": "ICC(2,1)",
            "score_a": "score A",
            "percentile": "percentile",
            "linked_b": "linked B",
            "ci_low": "CI low",
            "ci_high": "CI high",
            "subscale": "subscale",
        },
    },
    "zh": {
        "title": "{a} 与 {b} 对比",
        "meta": "- `{id}` v{version}：{n} 个条目，缺失处理={missing}，验证状态={validation}，sha256={hash}",
        "complete_pairs": "- 完整配对：**n = {n}**",
        "descriptives": "描述统计",
        "reliability": "内部一致性",
        "association": "相关性",
        "agreement": "一致性",
        "agreement_note": (
            "> Pearson 描述线性关联。ICC(2,1) 与 Bland-Altman 是辅助输出，"
            "解释绝对一致性需要有依据的共同分数尺度。不同尺度的原始分数"
            "不能据此认定可互换。标准化改变估计目标，不能证明原始分数可互换。"
        ),
        "classification": "分类一致性",
        "kappa": "κ = {kappa:.3f}，观察一致率 = {agreement:.3f}，n = {n}",
        "skipped_cutoffs": "已跳过：至少一个量表未定义切点。",
        "crosswalk": "等百分位链接（中位百分位秩与线性分位数插值）",
        "crosswalk_warning": (
            "> 警告：n < 100，链接分数不稳定。"
            "请报告置信区间，并仅作探索性解读。"
        ),
        "subscale_corr": "维度相关",
        "methods": "方法学段落（草稿）",
        "methods_text": (
            "> 使用 BRIDGE-D v{version}，按各量表声明的计分与缺失处理规则，"
            "计算 {a} 与 {b} 的得分。以 Pearson 描述主要线性关联，Spearman 作补充。"
            "ICC(2,1) 与 Bland-Altman 一致性界限作为辅助汇总，解释时要求有依据的共同分数尺度；"
            "分类一致性采用各量表已发表切点的 Cohen's κ；跨量表链接采用中位百分位秩"
            "与目标分数线性分位数插值，Bootstrap 重抽样 {n_boot} 次（n = {n}）。"
        ),
        "headers": {
            "scale": "量表",
            "n": "样本量",
            "mean": "均值",
            "sd": "标准差",
            "median": "中位数",
            "min": "最小值",
            "max": "最大值",
            "missing": "缺失",
            "alpha": "α",
            "pair": "量表对",
            "pearson": "Pearson",
            "spearman": "Spearman",
            "mean_diff": "均差",
            "sd_diff": "差的标准差",
            "loa_lower": "一致性下限",
            "loa_upper": "一致性上限",
            "icc21": "ICC(2,1)",
            "score_a": "A 分数",
            "percentile": "百分位",
            "linked_b": "链接到 B",
            "ci_low": "CI 下限",
            "ci_high": "CI 上限",
            "subscale": "维度",
        },
    },
}


def strings(lang: str) -> dict[str, object]:
    if lang not in STRINGS:
        raise ValueError(f"unsupported language {lang!r}; choose from {sorted(STRINGS)}")
    return STRINGS[lang]
