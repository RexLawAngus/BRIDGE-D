# 公开共同施测抑郁量表数据候选

检索日期：2026-11-19
目的：为 BRIDGE-D 的 empirical application 找一组同一批受试者同时施测的抑郁量表，用来演示从定义、计分到比较的完整流程。
筛选标准：至少两个抑郁严重度量表；个体数据；可以合法获取；样本量足以做链接（n ≥ 200）。

## 一、可直接下载

| 数据集 | 量表 | 样本 | 许可 | 链接 | 能否做量表链接 |
|---|---|---|---|---|---|
| NHANES 2017-2018 | PHQ-9 | 5,533 | 美国联邦公开数据 | [DPQ_J.XPT](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DPQ_J.XPT) | 不能。只有一个量表，可用于校准和单量表演示 |
| OpenNeuro ds003709 | MFQ + SHAPS | 青少年 MDD 与健康对照 | CC0 | [ds003709](https://openneuro.org/datasets/ds003709) | 不能。MFQ 测抑郁，SHAPS 测快感缺失，构念不同，只能做聚合/区分效度 |
| Zenodo 合成 TRD 数据 | HAM-D、PHQ-9、QIDS-SR16、MADRS | 1,000 名合成患者 | CC BY-NC 4.0 | [zenodo.17941503](https://zenodo.org/records/17941503) | 只能做管道测试。数据是合成的，不能当实证证据 |
| PROsetta Stone | PROMIS 与 legacy 量表的 crosswalk 表 | 聚合表 | 使用前查网站条款 | [prosettastone.org](https://www.prosettastone.org/) | 不能。没有个体数据，只能拿链接结果做外部对照 |

## 二、需申请并签数据使用协议

| 数据集 | 量表 | 样本 | 访问条件 | 链接 | 适合度 |
|---|---|---|---|---|---|
| CAN-BIND-01 | MADRS + PHQ-9，另有 GAD-7、DARS | 309（发布版本） | Brain-CODE 注册；提交数据访问申请；遵守 Brain-CODE Governance Policy；文件从 Brain-CODE 下载 | [CONP 页面](https://portal.conp.ca/dataset?id=projects/braincode_CAN-BIND_Biomarkers_for_Depression_Baseline_Data_Release)，[Brain-CODE](https://www.braincode.ca/) | 最合适。两个量表共同施测，基线加 Phase 1，样本量够做链接 |
| NESDA | IDS-SR + MADRS（MADRS 在住院子样本） | 3,348 | 提交分析计划；评审通过后签 Data Sharing Agreement；数据以 SPSS 格式提供 | [NESDA 数据访问](https://www.nesda.nl/researchers/about-nesda/)，[工具清单 PDF](https://www.nesda.nl/nesda/wp-content/uploads/2024/03/Table_instruments_NESDA.pdf) | 备选。样本大，但 MADRS 只在部分子样本，链接样本会缩小 |
| STAR*D | HAMD-17 + QIDS-SR16 | 约 4,000 | NIMH Data Archive 账号；机构签署 Data Use Certification；在 NDA 内检索 STAR*D | [NDA](https://nda.nih.gov/)，[DUC 说明](https://ndar.nih.gov/ndarpublicweb/Documents/NDAR+Data+Access+Request+DUC+FINAL.pdf) | 备选。量表组合经典，流程最长，需要导师或机构出面 |

## 三、需要联系作者或合作方

| 来源 | 内容 | 获取方式 | 说明 |
|---|---|---|---|
| 已发表的 IPD 元分析或 linking 研究 | 作者手里常有共同施测的个体数据 | 邮件联系通讯作者，说明用途，签数据使用协议 | 成功率取决于作者意愿和数据共享政策 |
| 导师或合作医院的队列 | PHQ-9 + HAMD 或其他组合 | 院内数据使用审批，匿名化后使用 | 最现实，速度取决于审批流程 |
| 量表原作者或翻译团队 | 中文版量表的常模或验证数据 | 联系作者，签授权协议 | 受版权和授权限制 |

## 结论

优先申请 **CAN-BIND-01**。MADRS 与 PHQ-9 在同一批受试者身上采集，样本 309，正好覆盖 BRIDGE-D 的核心场景：一个他评量表加一个自评量表。Brain-CODE 的申请流程明确，数据治理政策也公开。

**NESDA** 作为第二选择。样本最大，但 MADRS 只在住院子样本，链接分析的有效样本会明显小于 3,348。申请前先确认子样本量。

**STAR*D** 作为第三选择。HAMD-17 与 QIDS-SR16 是经典组合，但 NDA 的 Data Use Certification 需要机构签署，周期长。导师有 NDA 经验时值得走。

在申请等待期间，用 NHANES 的 PHQ-9 走通单量表流程，用 Zenodo 的合成数据测试共同施测的比较和链接。这两份数据不能进论文的实证部分。

## 检索记录

- Zenodo API：`HAMD AND MADRS` 返回 5 条，其中 4 条是论文，1 条是合成数据。没有找到真实的共同施测个体数据。
- Dryad API：`HAMD MADRS` 返回 0 条。
- OpenNeuro：ds003709 含 MFQ 与 SHAPS；ds003653 的 participants.json 只有人口学变量，没有量表总分。
- NESDA：仪器清单 PDF 确认 IDS 与 MADRS，MADRS 出现在住院研究（N4）。
- CAN-BIND：方案论文 Table 2 确认 MADRS（他评）与 PHQ-9（自评）共同施测。
- STAR*D：NDA 页面拒绝自动抓取，返回 403。量表组合和 DUC 要求来自公开资料，申请前需要在 NDA 内核对研究条目。

## 注意事项

1. 申请前核对量表版本、计分规则和语言版本。同一名称的量表可能有多个修订版。
2. 数据使用协议通常禁止再分发。论文只报聚合结果，不共享原始数据。
3. 链接分析要求两个量表测同一构念。MADRS 与 PHQ-9 都测抑郁严重度，可以做；MFQ 与 SHAPS 不行。
4. 样本量按 Level 2 的结果，n ≥ 200 时链接误差才接近 2 分。CAN-BIND 的 309 例够用，NESDA 的子样本需要先确认。
5. 不要把 SN-IPACS 的 42 份预实验数据写进论文的实证部分。
