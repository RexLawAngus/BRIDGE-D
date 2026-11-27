# BRIDGE-D v0.4.1 外部复现核对记录

核对日期：2026-11-22

## 材料

- 合作者提交的 `BRIDGE-D v0.4.1 复现验证说明文档.md`
- 合作者提交的 `results_comparison.csv`
- 本地代码快照：`c094984437ebb8e2f295c6db2f789ea4d0059402`
- Granwald 数据 SHA256：`f31cbd0a9949b2867e7294721e57f9502290cfee9445d8e73ddc15236e6949e1`
- NSDUH prepared CSV SHA256：`e065bd0964a3623bdbf9251dc2b1491bf0f251dbc5640a9ce13de9b87be3b8aa`

## 核对方法

在本地代码快照上重新运行测试套件、Granwald 主分析、Granwald 残差分析和 NSDUH 分析。将新生成的三个 JSON 结果与合作者 CSV 中的 38 个数值字段逐项映射，并计算本地值与合作者观测值的绝对差。

本地复跑环境：Python 3.13.9、numpy 2.3.5、pandas 2.3.3、scikit-learn 1.7.2、scipy 1.16.3。合作者报告的环境为 Python 3.14.4、numpy 2.5.5、pandas 3.1.1、scikit-learn 1.9.1。

## 结果

- 合作者测试结果为 `32/32 passed, 0 skipped`。本地结果为 `31/31 passed, 1 skipped`；本地未安装可选依赖 `python-docx`，符合任务书允许的结果。
- 两份输入数据的 SHA256 与任务书、合作者记录和本地文件一致。
- 合作者 CSV 中 38 个数值字段均能映射到本地输出，没有缺项。
- 本地值与合作者观测值的最大绝对差为 `5.551115123125783e-16`。
- 样本量、条目数、聚类数和精确置换划分数一致。
- Granwald 两项分析与 NSDUH 分析的方差、距离、相关系数、效应量和置换检验结果均满足任务书容差。

据此，可确认 v0.4.1 快照的数值结果在两套不同 Python 和科学计算库环境中复现。

## GitHub 版本核对

GitHub 上的公开标签 [`v0.4.1`](https://github.com/RexLawAngus/BRIDGE-D/tree/v0.4.1) 已核对，解析到提交 `c094984437ebb8e2f295c6db2f789ea4d0059402`。公开仓库、版本标签和本地核对所用快照一致。

合作者记录了工作目录 `BRIDGE-D-main`，没有保存 `git rev-parse HEAD` 或 `git describe` 的输出。其 38 个数值字段与 `v0.4.1` 标签对应提交的本地复跑结果一致，支持本次外部复现结论。

## 后续记录建议

1. 将复现任务书中的仓库地址从 `BRIDE-D.git` 改为 `BRIDGE-D.git`。
2. 后续复现记录保存完整 commit SHA；若使用源代码压缩包，同时保存压缩包 SHA256。
