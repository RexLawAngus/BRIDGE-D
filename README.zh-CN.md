# BRIDGE-D

[English](README.md) | 简体中文

**Bridging Instruments for Depression —— 把量表当作数据的计分、跨量表比较与经验条目地图工具。**

新量表不应该需要新代码。写一个 TOML 文件描述条目、反应选项、计分规则和切点，`bridged` 就能计分，并把它和同一批人做过的其他量表进行比较，也能根据回答模式绘制条目地图。

## 为什么

量表开发和跨量表比较在临床与健康研究中很常见，但流程通常每次从头搭：Excel 或 R 里计分，另一个脚本算一致性，第三个脚本做链接。底层工具其实都有（`psych`、`lavaan`、`equate`、`mirt`、`irr`），但缺一个小的、开源的、端到端的工作台，把量表当作数据来处理。

`bridged` 就是这个工作台。它不替代统计包，而是把每个人都要重写的那部分标准化：量表定义、计分规则、缺失处理策略、比较报告。

## 定位

BRIDGE-D 的长期方向，是成为心理测量工具共享的、版本化的定义层：让一个量表能够被机器和不同研究团队描述、验证、执行、比较和复用。

这是方向，不是对当前版本的声明。路径分三段：

| 阶段 | 含义 | 状态 |
|---|---|---|
| **现在** | 本地的“量表即数据”工具：用 TOML 定义量表、计分、与共同施测的量表比较，并生成探索性条目地图。 | 已具备 |
| **接下来** | 稳定标识（`id@version`）、内容哈希、验证状态，以及可跨项目校验定义的 registry。 | 计划中 |
| **长期** | 不同研究者和研究项目可以引用、核对、复用的共享定义层。 | 方向 |

价值不在于某一次分析省几分钟，而在于：两个都说“用了 PHQ-9”的研究者，指的是同一份可执行定义——同样的计分规则、同样的缺失处理、可核对来源。

BRIDGE-D 不替代 `psych`、`lavaan`、`equate`，不是临床诊断设备，也还不是 registry。

## 安装

需要 Python 3.11+（使用标准库 `tomllib`）、numpy 和 pandas。经验条目地图需要可选的 `map` 依赖。

```bash
pip install -e .
bridged --help

# 安装 PCA/MDS 条目地图和绘图依赖
pip install -e ".[map]"
```

如果 `bridged` 不在 PATH 里（Windows 常见），用模块入口：

```bash
python -m bridged --help
```

也可以完全跳过安装，直接在仓库根目录运行：

```bash
pip install numpy pandas
python -m bridged --help
```

## 快速开始

```bash
python examples/make_demo_data.py

bridged validate instruments/phq9.toml

bridged score \
  --instrument instruments/phq9.toml \
  --data examples/demo_cohort.csv \
  --out scores.csv

bridged compare \
  --a instruments/phq9.toml \
  --b instruments/example_new.toml \
  --data examples/demo_cohort.csv \
  --out report.md \
  --bootstrap 500

# 中文报告（默认英文）
bridged compare ... --lang zh

# 期刊格式的 Word 报告，带三线表
pip install -e ".[docx]"
bridged compare ... --lang zh --format docx --out report.docx
```

报告包含描述统计、内部一致性、相关性、ICC(2,1) 与 Bland-Altman 一致性、维度相关、分类一致性（Cohen's κ）、带 bootstrap 区间的等百分位链接，以及一段方法学草稿。

## 添加量表

### 基于条目

创建 `instruments/my_scale.toml`：

```toml
id = "my_scale"
name = "My New Instrument"
version = "0.1.0"
rater = "self"
recall = "past 2 weeks"
license = "CC-BY-4.0"

[response_scales.five_point]
levels = [0, 1, 2, 3, 4]
labels = ["Never", "Rarely", "Sometimes", "Often", "Always"]

[[items]]
id = "q1"
construct = "depressed_mood"
response = "five_point"

[[items]]
id = "q2"
construct = "anhedonia"
response = "five_point"
reverse = true

[scoring]
missing_min_answered = 1
missing_strategy = "prorate"

[scoring.total]
method = "sum"
items = "all"

[scoring.subscales.cognitive]
items = ["q1", "q2"]

[[cutoffs]]
label = "moderate"
min = 5
```

每个定义还应该声明来源与验证状态：

```toml
id = "my_scale"
version = "1.0.0"
source = "Author et al. 2024"
validation = "unverified"   # unverified | numerically-checked | source-verified
```

`bridged validate` 会打印定义哈希（`sha256`），每份报告会记录 `id@version` 和哈希前 12 位。条目、反应选项、计分规则、切点或缺失规则有任何改动，哈希都会变；改注释或空白不会。`source` 和 `validation` 是来源元数据，不参与哈希。

### 基于列

如果导出文件里已经有分数，直接指向列，而不是把条目加起来。这样，带自定义计分引擎的量表（游戏、任务、厂商导出）不用重新实现任何东西就能接入：

```toml
[scoring.total]
method = "column"
column = "total_score"

[scoring.subscales.mood]
column = "mood_score"

[[items]]
id = "total_score"
kind = "column"
column = "total_score"
```

## 模板与条目表

```bash
# 可填写的量表模板
bridged template --out instruments/my_scale.toml

# 从 CSV/XLSX 条目表生成量表定义
# 列名：id, text, construct, response, levels, reverse, subscale
bridged import-items \
  --items items.xlsx \
  --out instruments/my_scale.toml \
  --id my_scale --name "My New Instrument"
```

任何量表文件可以放在任何位置；把路径传给 `--instrument` / `--a` / `--b`。没有中央注册表要更新。

## 私有量表

不能公开的量表（未发表量表、专利申请中的方法、有版权的材料）放在 `private/`，它被 git 忽略：

```
private/
  my_scale.toml
  my_scale_cohort.csv
  my_scale_adapter.py
```

`private/` 不会进入发布包。发布前运行检查：

```bash
python scripts/check_public.py
```

它从 `private/forbidden.txt` 读取禁用词（每行一个），如果这些词出现在 `private/` 之外就失败。

## 经验条目地图

可选的条目地图模块根据共同施测条目的回答模式相似性，将条目放入连续的二维空间。当前实现使用 Spearman 条目相关、PCA 或非度量多维尺度分析和平均连接层次聚类，并用 Bootstrap 估计坐标与聚类稳定性。

```bash
pip install -e ".[map]"

bridged item-map \
  --instrument instruments/phq9.toml \
  --instrument instruments/example_new.toml \
  --data examples/demo_cohort.csv \
  --out map_output \
  --embedding pca \
  --bootstrap 200
```

`--embedding pca` 使用 Spearman 条目相关矩阵的前两个主成分载荷标定坐标，并报告解释方差。默认的 `--embedding mds` 保留非度量 MDS。层次聚类始终使用完整相关距离，不依赖二维投影，以免聚类结果被二维降维进一步压缩。

程序输出条目相关矩阵、距离矩阵、连续坐标、聚类归属、Bootstrap 共聚类概率、地图、树状图、量表投影覆盖足迹、量表间距离和方法报告。每张图同时输出 300 dpi PNG 和矢量 SVG。旧命令 `construct-map` 继续作为兼容别名。坐标表示当前样本中的回答模式相似性。两个坐标轴没有自动赋予心理学名称，也不代表已经发现了普适的症状空间。

预先定义的内容标签只能在地图拟合完成后进入检验：

```bash
# groups.csv: item,group；也可使用 instrument,item_id,group
bridged map-validate \
  --coordinates map_output/item_coordinates.csv \
  --groups groups.csv --out map_validation --permutations 9999

bridged map-compare \
  --reference sample_1/item_coordinates.csv \
  --candidate sample_2/item_coordinates.csv \
  --out cross_sample_comparison
```

`map-validate` 输出各组质心、全局组间方差比例、两两质心距离与置换检验；标签不会改变已拟合坐标。`map-compare` 通过 Procrustes 对齐比较两张地图，报告坐标 RMSE、对齐后坐标轴相关、标准化残差和成对距离相关。两个命令都会同时写出 300 dpi PNG 和矢量 SVG。这些指标用于稳定性与解释检查，不等同于验证性潜变量模型。

可复现验证位于
[`validation/construct_map_granwald`](validation/construct_map_granwald) 和
[`validation/construct_map_nsduh`](validation/construct_map_nsduh)。如果二维总图压缩了较窄的内容对比，只传入需要检查的量表即可生成局部图。

## 模拟

`simulate` 生成真值已知的数据：你设定两个量表潜变量之间的相关、条目载荷、反应格式和样本量；工具写出数据集、总体真值，以及（可选的）多次重复的恢复研究。

```bash
bridged simulate --config examples/sim.toml --out sim/

# 给定 n 的恢复/精度研究
bridged simulate \
  --config examples/sim.toml \
  --out sim_n200 --n 200 --replications 300
```

输出：

- `data.csv`：一份包含两个量表条目的合成队列
- `truth.json`：总体相关、ICC 和链接表
- `recovery.csv` + `summary.json`（当 `replications > 1`）：偏差、CI 覆盖率、平均 CI 宽度、各次重复的链接 RMSE

配置：

```toml
n = 200
seed = 42
replications = 300

[model]
latent_r = 0.5        # 两个量表潜变量之间的相关

[instrument_a]
id = "a"
items = 6
levels = 5
loadings = [0.75, 0.55, 0.80, 0.65, 0.70, 0.45]

[instrument_b]
id = "b"
items = 9
levels = 4
loading = 0.65
```

`latent_r` 是两个潜在特质之间的相关；观察到的总分相关会因为测量误差而更低。这个差距正是重点：它让你看到你的设计能容忍多少衰减。

合成数据用于软件验证和样本量规划，不是关于真实量表的证据。

## 发布与留档

每次版本号变更都先做一份不可变快照：

1. 修改 `pyproject.toml` 里的 `version`。
2. 运行 `python tests/run_tests.py` 和 `python scripts/check_public.py`。
3. 提交这次版本变更。
4. 运行 `python scripts/archive_version.py`。

脚本把 `git archive HEAD` 导出到 `releases/v<version>-<date>`，写入带 commit hash 的 `RELEASE.json`，并拒绝覆盖已有留档。只有已提交的文件会被导出，所以 `private/` 和生成物不会进入发布。

要存到别处（比如外置硬盘），传 `--base`，或把路径写进被 git 忽略的 `.archive-dir` 文件：

```bash
python scripts/archive_version.py --base "D:/archives/BRIDGE-D"
```

当 `pyproject.toml` 的版本号变化时，post-commit 钩子会自动做这件事。每个克隆启用一次：

```bash
git config core.hooksPath .githooks
```

## 验证

Level 1 在固定数据上把核心统计量与 R（`psych`、`irr`）对照：

```bash
python validation/level1/make_fixture.py
Rscript validation/level1/reference.R
python validation/level1/run_level1.py
```

容差和最新结果见 [`validation/level1/README.md`](validation/level1/README.md)。基于模拟的检查（Level 2）在 `bridged simulate` 里。论文的统计审查包在 [`docs/statistical_review_packet.md`](docs/statistical_review_packet.md)。端到端应用流程（NHANES 加合成伴随量表）在 [`validation/application/`](validation/application/README.md)。

## 测试

```bash
python tests/run_tests.py
```

## 范围与限制

- 链接目前只有等百分位。IRT 共校准是计划，不是已实现。
- 原始分数上的 Bland-Altman 假设同一量纲；量程不同时只能作描述性参考，不能当作一致性结论。
- 切点完全由量表文件声明。发表结果前请对照原始文献核验。
- 演示量表 `example_new.toml` 是合成的，必须替换。
- 条目地图坐标与量表投影覆盖足迹会受到样本、缺失情况和回答分布影响。聚类和距离属于探索性结果，不能直接解释为临床亚型或已验证的潜在构念坐标。

## 许可

代码用 MIT。量表定义各自带自己的许可；内置的 PHQ-9 和 HAMD-17 文件只包含条目名称，不包含受版权保护的锚点描述。
