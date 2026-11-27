"""Independent, descriptive anchor demonstrations; never combine datasets."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bridged import __version__
from bridged.anchor_analysis import analyze_anchor_items, write_anchor_analysis, plot_anchor_neighborhood
from bridged.construct_map import collect_item_values, fit_construct_map
from bridged.instrument import Instrument

CODEBOOK = "https://www.samhsa.gov/data/system/files/media-puf-file/nsduh-2021_2024-ds0001-info-codebook_v1.pdf"


def load_preparation(name):
    path = ROOT / "validation" / f"construct_map_{name}" / "run_pca.py"
    spec = importlib.util.spec_from_file_location(f"prepare_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def granwald(data_path):
    module = load_preparation("granwald")
    raw = pd.read_csv(data_path)
    for column in ["PHQ_9", "SDS_19"]:
        if column not in raw:
            raise ValueError(f"missing verified source column: {column}")
    data = module.prepare_data(data_path)
    configs = [ROOT / "instruments/phq9.toml",
               module.HERE / "instruments/cesd20.toml", module.HERE / "instruments/sds20.toml"]
    instruments = [Instrument.load(p) for p in configs]
    values, meta = collect_item_values(instruments, data)
    anchors = [meta.loc[meta.item_id.eq(i), "item"].item() for i in ["phq9", "sds19"]]
    tags = pd.read_csv(module.HERE / "semantic_tags.csv").merge(meta, on=["instrument", "item_id"], validate="one_to_one")
    groups = pd.concat([pd.DataFrame({"item": tags.item, "group_set": name,
                                     "group": np.where(tags[name].eq(1), name, f"non_{name}")})
                        for name in ["somatic", "interpersonal"]], ignore_index=True)
    return data, instruments, anchors, groups, {anchors[0]: 0, anchors[1]: 1}, dict(
        source_columns=["PHQ_9", "SDS_19"], raw_n=len(raw), analysis_n=len(data),
        selection="AC_fails <= 2; identical scoring and selection to existing map",
        positive_rule="PHQ_9 > 0; SDS_19 > 1 (scored minimum=1)",
        config_files=[str(p) for p in configs], label_file=str(module.HERE / "semantic_tags.csv"),
        source=str(data_path))


def nsduh(raw_path, prepared_path):
    module = load_preparation("nsduh")
    base = pd.read_csv(prepared_path, dtype={"QUESTID2": "string"})
    usecols = ["YEAR", "QUESTID2", "SUICTHNK"]
    parts = []
    # Read only the verified columns, then match respondents within this dataset.
    for chunk in pd.read_csv(raw_path, sep="\t", usecols=usecols,
                             dtype={"QUESTID2": "string"}, chunksize=25000):
        parts.append(chunk)
    anchor_data = pd.concat(parts, ignore_index=True)
    joined = base.merge(anchor_data, on=["YEAR", "QUESTID2"], how="left", validate="one_to_one", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise ValueError("some prepared participants lack a source match")
    raw_counts = joined.SUICTHNK.value_counts(dropna=False).to_dict()
    joined["suic_ideation"] = pd.to_numeric(joined.SUICTHNK, errors="coerce").map({1: 1., 2: 0.})
    data = joined.dropna(subset=["suic_ideation"]).reset_index(drop=True)
    configs = [module.HERE / "instruments/nsduh_mde8.toml", module.HERE / "instruments/nsduh_sds4.toml"]
    instruments = [Instrument.load(p) for p in configs]
    instruments.append(Instrument.from_dict({
        "id": "nsduh_ideation", "name": "NSDUH observed past-year serious ideation",
        "version": "2021-2024", "recall": "past year", "source": CODEBOOK,
        "response_scales": {"binary": {"levels": [0, 1]}},
        "items": [{"id": "suic_ideation", "response": "binary"}],
        "scoring": {"total": {"method": "sum", "items": "all"}},
    }))
    _, meta = collect_item_values(instruments, data)
    anchors = meta.loc[meta.instrument.eq("nsduh_ideation"), "item"].tolist()
    groups = meta.loc[~meta.item.isin(anchors), ["item", "construct"]].rename(columns={"construct": "group"})
    return data, instruments, anchors, groups, {}, dict(
        source_columns=["SUICTHNK"], source=str(raw_path), prepared_source=str(prepared_path),
        prepared_n=len(base), analysis_n=len(data), anchor_missing_excluded=len(base)-len(data),
        raw_anchor_codes_in_prepared_sample={str(k): int(v) for k, v in raw_counts.items()},
        selection="existing complete-case adult past-year MDE sample, plus observed SUICTHNK 1/2",
        recoding="SUICTHNK: 1 -> 1, 2 -> 0, all other codes -> missing; no imputed duplicate anchor",
        map="13 indicators: original 12 plus ideation, newly fitted PCA using unchanged core",
        config_files=[str(p) for p in configs], codebook=CODEBOOK,
        convergence="not applicable: one independent ideation anchor",
        survey_design="unweighted participant bootstrap; descriptive sample analysis, not national prevalence")


def run_one(name, prepared, args):
    data, instruments, anchors, groups, thresholds, provenance = prepared
    print(f"{name}: n={len(data)}, fitting PCA and analyzing anchors", flush=True)
    fitted = fit_construct_map(instruments, data, embedding="pca", bootstrap=0, seed=args.seed)
    values, _ = collect_item_values(instruments, data)
    result = analyze_anchor_items(fitted, values, anchors, groups=groups,
                                  positive_thresholds=thresholds, bootstrap=args.bootstrap,
                                  permutations=args.permutations, seed=args.seed)
    out = args.out / name
    write_anchor_analysis(result, out)
    plot_anchor_neighborhood(fitted, result, out / "anchor_map")
    fitted.coordinates.to_csv(out / "item_coordinates.csv", index=False)
    fitted.associations.rename_axis("item").to_csv(out / "item_associations.csv")
    fitted.distances.rename_axis("item").to_csv(out / "item_distances.csv")
    (out / "analysis_config.json").write_text(json.dumps(fitted.metrics, indent=2), encoding="utf-8")
    groups.to_csv(out / "content_groups.csv", index=False)
    hashes = {}
    for path in [provenance["source"], *provenance["config_files"],
                 *[provenance[k] for k in ["prepared_source", "label_file"] if k in provenance]]:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024*1024), b""):
                digest.update(block)
        hashes[str(path)] = digest.hexdigest()
    provenance.update(version=__version__, source_sha256=hashes,
                      definitions=[{"id": i.id, "version": i.version, "sha256": i.definition_hash()} for i in instruments],
                      settings=result.settings)
    (out / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, provenance


def summary(results, args):
    lines = ["# 锚定条目应用示范（BRIDGE-D 0.5.1）", "",
             f"两套数据独立拟合与分析。参与者 Bootstrap {args.bootstrap} 次；标签置换 {args.permutations} 次；随机种子 {args.seed}。",
             "完整空间距离为 1−Spearman r；质心距离指二维 PCA 投影。置换 p 为单侧邻近检验，未经多重比较校正。跨量表百分位是描述性排名，不是显著性检验。", ""]
    for name, (result, provenance) in results.items():
        lines += [f"## {name}（n = {provenance['analysis_n']}）", "",
                  "|锚点|有效数|阳性人数|阳性率|均值|标准差|中位数|IQR|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in result.distributions.itertuples():
            lines.append(f"|{r.anchor}|{r.n_valid}|{r.positive_n}|{r.positive_rate:.2%}|{r.mean:.3f}|{r.sd:.3f}|{r.median:.3f}|{r.iqr:.3f}|")
        lines += ["", "阳性定义：" + provenance.get("positive_rule", provenance.get("recoding", "")) + "。", ""]
        if name == "NSDUH":
            lines += [f"由原 12 指标完整样本 {provenance['prepared_n']} 人中排除意念作答缺失/无效的 {provenance['anchor_missing_excluded']} 人。加入意念指标后另拟合 13 指标地图，不能直接沿用图 4 的二维坐标。", "",
                      "只有一个独立意念锚点，跨量表锚点收敛度不适用。未使用调查权重；本次比例仅描述所选样本。", ""]
        for r in result.convergence.itertuples():
            lines += [f"跨量表锚点：r = {r.spearman_r:.4f}（95% CI {r.r_ci_low:.4f}–{r.r_ci_high:.4f}），1−r = {r.distance_1_minus_r:.4f}，二维距离 = {r.distance_2d:.4f}；在 {r.cross_scale_pair_count} 对跨量表条目中的距离百分位为 {r.cross_scale_distance_percentile:.2f}%（越低越近）。", ""]
        lines += ["### Top-5 邻近条目", "", "|锚点|邻居|r [95% CI]|1−r|二维距离|Top-10 稳定性|", "|---|---|---:|---:|---:|---:|"]
        for r in result.neighbors.loc[result.neighbors['rank'].le(5)].itertuples():
            lines.append(f"|{r.anchor}|{r.neighbor}|{r.spearman_r:.4f} [{r.r_ci_low:.4f}, {r.r_ci_high:.4f}]|{r.distance_1_minus_r:.4f}|{r.distance_2d:.4f}|{r.top_k_stability:.1%}|")
        lines += ["", "### 预设内容组邻近度", "", "|锚点|标签体系/组|组条目数|平均1−r|p|二维质心距离|p|", "|---|---|---:|---:|---:|---:|---:|"]
        for r in result.groups.itertuples():
            lines.append(f"|{r.anchor}|{r.group_set}/{r.group}|{r.n_items}|{r.mean_distance_1_minus_r:.4f}|{r.p_mean_distance:.4f}|{r.centroid_distance_2d:.4f}|{r.p_centroid_2d:.4f}|")
        lines += ["", "全部锚点从内容组与置换池剔除；各标签体系单独置换，保持组大小。", ""]
    g = results["Granwald"][0]
    n = results["NSDUH"][0]
    lines += ["## 两套数据的对照", "",
              "Granwald 在同一批参与者内检验两个量表锚点的收敛；NSDUH 只检查单个过去一年意念指标相对症状和功能领域的位置。两套样本的时间窗、选样和反应格式不同，不能把距离或阳性率的差异解释为相同构念的总体差异。", ""]
    for name, result in [("Granwald", g), ("NSDUH", n)]:
        for anchor, rows in result.groups.groupby("anchor", sort=False):
            nearest = rows.loc[rows.mean_distance_1_minus_r.idxmin()]
            lines.append(f"{name}：{anchor} 到预设组中平均完整距离最小的组为 {nearest['group']}（1−r = {nearest.mean_distance_1_minus_r:.4f}，p = {nearest.p_mean_distance:.4f}）。")
    lines += ["", "完整平均距离与二维质心距离的检验可能不同，需并列阅读上述数值，不能仅按二维点位解释完整空间。", ""]
    rates = [r.positive_rate for result in [g, n] for r in result.distributions.itertuples()]
    lines.append(f"低发生率提示：本次锚点的样本阳性率范围为 {min(rates):.2%}–{max(rates):.2%}。更低发生率的应用需检查有效重抽样次数；常数列不能建立邻域。")
    for name, result in [("Granwald", g), ("NSDUH", n)]:
        for anchor, rows in result.neighbors.groupby("anchor", sort=False):
            lines.append(f"{name} {anchor}：完整锚点相关行有效重抽样 {int(rows.iloc[0].bootstrap_anchor_valid)}/{args.bootstrap} 次。")
    lines += ["", f"编码依据：[SAMHSA 合并数据代码簿]({CODEBOOK})；原始列名与实测编码频数、样本选择、文件哈希见各数据集 provenance.json。", ""]
    args.summary.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    datasets = ROOT.parents[1] / "公开数据集"
    parser.add_argument("--granwald-data", type=Path, default=datasets / "granwald_2025_PHQ9_CESD_SDS/extracted_data_networkPriors.csv")
    parser.add_argument("--nsduh-raw", type=Path, default=datasets / "nsduh_2021_2024_mde_social_function/raw_tsv/NSDUH_2021_2024_Tab.txt")
    parser.add_argument("--nsduh-prepared", type=Path, default=datasets / "nsduh_2021_2024_mde_social_function/analysis/nsduh_adult_mde_construct_map.csv")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--permutations", type=int, default=9999)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--out", type=Path, default=HERE / "outputs")
    parser.add_argument("--summary", type=Path, default=HERE / "RESULTS_ANCHOR_DEMO.zh-CN.md")
    args = parser.parse_args(argv)
    results = {}
    results["Granwald"] = run_one("Granwald", granwald(args.granwald_data), args)
    results["NSDUH"] = run_one("NSDUH", nsduh(args.nsduh_raw, args.nsduh_prepared), args)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    summary(results, args)
    print(f"wrote {args.summary}", flush=True)


if __name__ == "__main__":
    main()
