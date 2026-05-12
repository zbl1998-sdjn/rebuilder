# ReBuilder 项目交接文档

更新时间：2026-05-10

## 一句话概括

ReBuilder 是一个面向 ProgramBench 的 cleanroom 程序重建架构实验。它的目标不是证明某个大模型更强，而是验证：在严格遵守测试集设计哲学的前提下，通过更好的 agent 架构、探测、证据管理、实现约束、差分测试和修复流程，是否能让当前模型在传统“暴力堆参数”之外取得可复现的改进。

当前项目已经从原型走到“完整闭环可运行”的阶段：

```text
task_cleanroom image -> probe reference -> synthesize spec -> design architecture
-> generate replacement -> differential test -> repair -> holdout gate -> package/report
```

但它还没有到“泛化稳定”阶段。当前已经拿到三个官方 aggregate 基线：zoxide 37、zip-password-finder 26、cmatrix 77；接下来的重点是继续扩展跨任务信号，而不是只追单任务 exploration。

## 最高优先级边界

后续所有优化都必须服从 ProgramBench cleanroom 哲学和项目的 anti-overfit 边界。这个边界比短期分数更重要。

允许使用：

- cleanroom workspace 中自带的文档
- 对 reference executable 的普通黑盒执行
- CLI args、stdin、stdout、stderr、exit code
- 文件系统输入输出和副作用
- 官方 `:task_cleanroom` 镜像
- exploration split 的详细失败报告，用于修复同一轮 cleanroom 重建

禁止使用：

- 原始源码、fork、镜像仓库、包源码、本地 dependency cache
- 反编译、反汇编、trace、binary instrumentation
- 包装、复制、调用或提交 reference executable
- 官方 hidden eval 的详细失败信息
- internal holdout 的详细失败信息进入 repair
- official `:task` 镜像在 inference 阶段使用
- 把 query/add/remove/import、状态行为、文件变换、holdout 失败或官方隐藏失败做成 lookup table

internal holdout 只能作为 aggregate-only 泛化估计。official eval 只能作为最终 aggregate summary。任何用隐藏失败反推实现的做法都应视为破坏实验。

## 项目为什么存在

ProgramBench 的价值在于它测试的是“给定有限可见材料，重建真实程序行为”的能力，而不是普通代码题。很多顶尖模型在部分任务上可能得到 0%，说明问题不只是模型参数规模，还涉及：

- 如何从文档和黑盒行为中采集证据
- 如何把证据转成可执行规格
- 如何让模型避免一次性写出不稳定的大文件
- 如何通过差分测试定位行为缺口
- 如何防止过拟合测试样本
- 如何把 repair 限制在合规证据范围内

ReBuilder 的研究假设是：

```text
对长链路、不完整信息的软件重建任务，agent 架构和流程设计可能比单纯扩大模型参数更关键。
```

因此项目应该用 cleanroom、aggregate、可复现实验来评价，而不是围绕单个任务手工调到过拟合。

## 当前实现情况

### 核心流水线

核心由 `MetaController` 调度：

```text
ProbeEngine
  -> SpecSynthesizer
  -> ArchitectAgent
  -> ImplementerAgent
  -> DifferentialTester
  -> RepairLoop
```

主要模块：

- `core/probe_engine.py`：黑盒探测入口
- `core/spec_synthesizer.py`：从文档和行为证据生成规格
- `core/architect_agent.py`：设计实现架构
- `core/implementer_agent.py`：生成代码，支持 Python staged generation
- `core/differential_tester.py`：reference 与 replacement 差分测试
- `core/repair_loop.py`：基于 exploration 失败聚类生成修复
- `core/execution`：本地、Docker、WSL 执行后端
- `core/probing`：stateful、shell init、file I/O 等探测策略
- `core/implementation`：静态资产注入和 guardrail
- `core/submission`：ProgramBench 风格提交打包
- `core/evaluation`：官方 aggregate eval summary 与 exploration failure report
- `core/experiments`：mini-lab 聚合报告

### 已完成能力

- Windows + Docker Desktop 下可运行官方 cleanroom task
- GLM-5.1 coding-plan endpoint 已接通，配置在 `config/smoke_glm.yaml`
- 支持 `.env` 加载 API key
- 支持 Docker reference backend，并强制 reference 镜像为 `:task_cleanroom`
- 支持 WSL replacement executor，用于在 Windows 主机上更接近 Linux 官方环境
- 有 run-session 目录布局和 evidence store
- 能 fetch ProgramBench sample metadata 并 prepare cleanroom workspace
- 有 internal exploration/holdout split
- holdout 默认只输出 aggregate，不暴露详细失败
- repair 使用 exploration failure cluster，不使用 holdout/official hidden 细节
- 支持 official eval aggregate summary 和 baseline record
- 支持 submission packaging，并用 holdout gate 拒绝弱泛化候选
- 支持 mini-lab 多任务聚合
- 支持 generated-code integrity check
- Implementer 解析更稳健，支持 JSON、近似 JSON、nested code fences
- Python staged implementation：先生成 runnable CLI entrypoint，再生成 support modules
- 支持 stateful cleanroom probes 和 shared workdir replay
- 支持 shell init full-output probes
- 支持 file I/O side-effect probes 和 output file preview contract
- 支持项目内 Python 3.12 `.venv` 基线，`pytest -q` 只收集 `tests/`
- 支持静态输出资产注入，但只允许非常窄的默认 `init <shell>` deterministic 长输出
- 静态资产可通过 CLI/config 开关做 ablation
- 静态资产模式已添加 prompt guard，要求模型不要手写大段 shell init 模板，而是生成 compact CLI skeleton
- file I/O probing 已覆盖 documented output directory 场景
- phase-level LLM usage metadata 已可写入结果元数据（前提是 provider 返回 usage）

当前全量单测：

```text
173 passed
```

## 当前实验状态

主要任务：`ajeetdsouza__zoxide.67ca1bc`

cleanroom workspace：

```text
runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace
```

reference image：

```text
programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom
```

### 官方基线

当前冻结的 zoxide 官方 evaluator baseline：

```text
175/974
score 18
pass_rate 0.17967145790554415
```

这是一个真实官方 aggregate 非零基线，但不是 solved task：

```text
fully_resolved=False
almost_resolved=False
```

近期官方候选低于冻结基线：

```text
95/577
76/577
78/577
```

所以不能升级 official baseline。

### 本地烟测与 holdout

历史上，本地 exploration-only 指标曾到：

```text
83.3% local differential
100.0% stateful WSL local differential
```

这些不是官方隐藏测试结果，也不是泛化成功。

最新 holdout-gated WSL zoxide smoke：

```text
runs\ablation_assets_on_retry_20260510\generated\ajeetdsouza__zoxide.67ca1bc\result.json
```

结果：

```text
status: failed
resolved_rate: 0.76
holdout_resolved_rate: 0.2857142857142857
probes_conducted: 27
exploration_cases: 20
holdout_cases: 7
static_output_assets_enabled: true
contract_asset_status: materialized
contract_asset_count: 2
```

解释：

- 这次修复成功解决了 assets-enabled 之前的 `no_files` 实现失败
- 实现阶段现在能生成可解析代码并 materialize 静态资产
- repair 后 exploration 达到 `76.0%`
- holdout 仍只有 `2/7 = 28.6%`
- packaging gate 正确拒绝它，不应提交官方 eval

## 最近完成的关键修复

问题：assets-enabled ablation 曾让模型试图手写巨大 shell init 输出，导致实现响应过长、截断、不可解析，最终 `no_files`。

已完成修复：

- 在 `core/implementer_agent.py` 增加 `_static_asset_generation_guard`
- 当静态资产启用且存在可物化 shell init 契约时，系统提示明确要求：
  - 不要实现 shell init script templates
  - 不要输出 completion scripts 或大段 shell/Powershell bodies
  - exact `init <shell>` argv forms 由 generated asset injection 处理
  - entrypoint 保持 compact
  - 只实现普通 CLI dispatch、状态逻辑、错误和非静态行为
- guard 已覆盖：
  - single-pass implementation
  - staged entrypoint generation
  - staged support generation
  - retry implementation
- 增加回归测试：
  - `test_static_asset_entrypoint_prompt_bans_shell_init_template_generation`
  - `test_static_asset_retry_prompt_bans_shell_init_template_generation`

验证：

```powershell
pytest -q
```

结果：

```text
173 passed
```

## 重要文件和目录

项目入口：

```text
main.py
```

配置：

```text
config\settings.yaml
config\smoke_glm.yaml
.env
```

合规与运行文档：

```text
docs\programbench-compliance.md
docs\programbench-cleanroom-runbook.md
docs\handoff.md
```

zoxide cleanroom task：

```text
runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc
```

最新 assets-enabled smoke：

```text
runs\ablation_assets_on_retry_20260510
```

官方 baseline：

```text
baselines\programbench
```

## 常用命令

运行全量测试：

```powershell
cd C:\Users\Administrator\Desktop\ReBuilder
pytest -q
```

运行 mock smoke：

```powershell
python main.py --task examples\mock_task --config config\smoke_glm.yaml --output runs\smoke_glm_mock --max-repairs 1
```

准备 zoxide cleanroom workspace：

```powershell
python scripts\prepare_programbench_task.py ajeetdsouza__zoxide.67ca1bc --runs runs\programbench_smoke --pull
```

运行 zoxide WSL smoke：

```powershell
python main.py `
  --task runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace `
  --config config\smoke_glm.yaml `
  --output runs\zoxide_next_smoke `
  --max-repairs 1 `
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom `
  --replacement-executor wsl
```

运行静态资产 ablation：

```powershell
python main.py `
  --task runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace `
  --config config\smoke_glm.yaml `
  --output runs\ablation_assets_on_next `
  --max-repairs 1 `
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom `
  --replacement-executor wsl `
  --static-output-assets enabled

python main.py `
  --task runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace `
  --config config\smoke_glm.yaml `
  --output runs\ablation_assets_off_next `
  --max-repairs 1 `
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom `
  --replacement-executor wsl `
  --static-output-assets disabled
```

## 当前风险

### 1. 本地 exploration 分数和官方分数存在明显 gap

本地 exploration 分数可以很高，但官方 aggregate 仍低。这说明当前 probes 和 validation corpus 还不能充分覆盖官方隐藏行为。不要用 exploration 分数作为突破依据。

### 2. holdout 仍弱

最新 `76.0%` exploration 只有 `28.6%` holdout。说明 repair 有效解决了已观察 exploration failure，但泛化不足。

### 3. 静态资产机制需要持续审慎

静态资产只应处理长、确定、文档化、默认 `init <shell>` 输出。它是架构优化，不是测试样本表。每次声称收益前必须做 assets-on/off ablation。

### 4. zoxide 单任务风险

围绕一个任务持续优化容易产生隐性过拟合。下一阶段必须扩大 mini-lab，到更多 ProgramBench cleanroom tasks 上看 cross-task 信号。

### 5. Windows/WSL/Docker 环境差异

Windows 主机上 reference 是 Docker Linux，replacement 推荐 WSL。路径、换行、文件权限、临时目录都可能造成差分误差。

## 下一步应该做什么

### P0：不要破坏 cleanroom 和 anti-overfit 边界

每次新增 probe、repair、asset 或 package 逻辑前，先检查：

- 是否只使用 cleanroom 可见材料
- 是否会把 holdout 细节带进 repair
- 是否会把 official hidden failure 带进实现
- 是否把某类行为变成 lookup table
- 是否需要 assets-on/off ablation

### P1：提升泛化，而不是继续追 zoxide exploration

当前最重要的指标是 internal holdout 和跨任务 mini-lab，不是 zoxide exploration。

建议做：

- 扩大 probe diversity，但仍来自文档和黑盒正常执行
- 改进 probe corpus split，让 stateful plan 原子性继续保持
- 增加更多自然变体，而不是针对失败样例补丁
- 记录每类 probe 对 holdout 的 aggregate 影响

### P2：做更多 cleanroom task mini-lab

至少选 2 到 5 个不同类型任务：

- CLI/stateful database 类
- 文件输入输出类
- 文本处理类
- 参数解析复杂类
- 可能涉及 compiled language 的任务

目标不是马上提高平均分，而是找出 ReBuilder 哪些模块对不同任务稳定有效。

### P3：改进 file I/O 和 config/cache side-effect probes

当前已有基础 file I/O probe，但还需要：

- 目录输出
- 多文件输出
- config 文件
- cache/data directory
- env var 控制路径
- 文件权限和不存在路径
- stdout/stderr 与文件输出同时存在的场景

这些能力更可能提升跨任务泛化。

### P4：改进实现阶段的结构化约束

现在 staged Python generation 已经比一次性生成稳定，但还可以继续做：

- 更强的 output budget planning
- entrypoint/support 文件职责显式化
- 生成后自动检查 CLI dispatch 覆盖
- 对超大 contract 自动摘要或资产化
- 对不应资产化的行为强制走逻辑实现

### P5：增强 repair 的泛化意识

repair 现在基于 exploration failure clusters。下一步应增加：

- 修复前后的非回归解释
- cluster 到行为类别的映射
- 修复是否可能污染 holdout 的风险标记
- 只允许修复“规则类问题”，降低修复单例样本的倾向

### P6：完善实验记录和成本记录

建议在每次 run 记录：

- LLM provider/model/base_url
- token/cost/latency
- probes count 和 split
- implementation parse status
- repair cluster
- exploration/holdout aggregate
- static assets on/off
- 是否 package
- 是否 official eval
- baseline 是否升级

这能让后续判断“架构优化是否有效”更可信。

## 推荐的下一次实施顺序

1. 保持当前 zoxide baseline 不变，不提交最新 weak-holdout candidate。
2. 选 2 到 3 个新 ProgramBench cleanroom tasks，跑 mini-lab smoke。
3. 汇总每个任务失败阶段：probe、spec、implementation、validation、holdout。
4. 找到跨任务共同缺口，优先做 shared architecture 改进。
5. 对任何改进做 ablation，并记录 aggregate-only 结果。
6. 只有当 holdout gate 足够强时，才 package official candidate。
7. official eval 后只记录 aggregate summary 和 submission hash，不把详细 hidden 失败用于修复。

## 当前结论

ReBuilder 已经证明了两件事：

1. 在 strict cleanroom 边界下，完整 reconstruction loop 可以跑通，并且 zoxide 官方 eval 已有非零 baseline。
2. 架构层改进确实能解决一些模型单独生成时的失败模式，例如实现阶段截断、shell init 长输出失控、repair 非回归控制和 holdout gate。

但还不能证明：

1. 当前架构已经稳定优于单模型。
2. 最新本地高 exploration 分数代表官方隐藏测试突破。
3. 静态资产带来的收益已经具备跨任务泛化。

下一阶段的核心任务是从“单任务可运行”推进到“多任务可复现、可 ablation、holdout 更强”的研究状态。
