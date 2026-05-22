# ReBuilder 项目交接文档

更新时间：2026-05-22

## 一句话概括

ReBuilder 是一个面向 ProgramBench 的 cleanroom 程序重建架构实验。它的目标不是证明某个大模型更强，而是验证：在严格遵守测试集设计哲学的前提下，通过更好的 agent 架构、探测、证据管理、实现约束、差分测试和修复流程，是否能让当前模型在传统“暴力堆参数”之外取得可复现的改进。

当前项目已经从原型走到“完整闭环可运行”的阶段：

```text
task_cleanroom image -> probe reference -> synthesize spec -> design architecture
-> generate replacement -> differential test -> repair -> holdout gate -> package/report
```

但它还没有到“泛化稳定”阶段。当前已经拿到多项官方 aggregate 基线，包括 zoxide 37、go-mod-outdated 94、htmlq 91、cmatrix 95、csview 87、chmln sd 86、nnn 79、elfcat 66、gron 62、clog-cli 45、xsv 44、zip-password-finder 40，以及历史低样本的 chroma 3；接下来的重点是继续扩展跨任务信号，而不是只追单任务 exploration。

最新重要增量：2026-05-22 继续按用户要求的 no-external `file_bridge` /
子代理路径推进 `rbakbashev__elfcat.52f8cc7`，没有调用 Kimi/GLM/外部 LLM，
只把推理和实现放在 ReBuilder 本地官方标准闭环内。先复跑
`reference_html_patch3` 官方 eval：本地仍为 exploration `119/119`、holdout
`17/18`，但 ProgramBench official eval 在 `3600` 秒后没有写出 `.eval.json`，
只生成 `official_eval_failure_report.json`，因此 patch3 仍只能作为 official-eval
operational failure 证据，不能算官方分数。

随后按 TDD 增加 `reference_html_patch4`：大文件场景下把 HTML bytes panel 限制为
header-only，避免对完整文件做超大字节 span 渲染；新增大文件回归先红后绿。验证：
`py_compile` 通过，`python -m ruff check --no-cache ...` 通过，提升权限 focused
pytest `tests\test_elfcat_file_bridge_harness.py` 为 `12 passed`。本地
no-external ReBuilder gate 为 exploration `119/119`、holdout `17/18`，runtime
smoke 覆盖 `args/default/input_files/stdin`。ProgramBench official eval 完成：
counted `371/564`、score `66`；raw `445/646`、score `69`。这把 elfcat 官方
aggregate baseline 从 score `56` 升到 `66`，但仍不是 solved/fully resolved。
baseline 已更新到
`baselines\programbench\rbakbashev__elfcat.52f8cc7.baseline.json`，submission
SHA-256 为 `1ed17b9d3c85b4b987a0f92be921e63cf42a169fa756f8a92eb91d9d1b35dbf9`。
更新后 strict official-ready ranker 仍为 `row_count=0`；当前候选被
`official_not_above_baseline` 阻断，说明它已经等于最新记录 baseline，而不是还有
可重复提交的 ready 行。不要在交接或公开材料里写 hidden official case 细节。

此前重要增量：2026-05-22 继续按 no-external `file_bridge` 路径复核
`burntsushi__xsv.f430466` 的本地泛化缺口。本轮仍没有使用 Kimi/GLM/外部 LLM；
推理响应只通过 ReBuilder 的本地 `file_bridge` harness 写入 request/response 文件。
先补了 official closed-loop/runner 侧 gate：`0/0` 或缺 `.eval.json` 的 ProgramBench
结果现在被归为 official-eval operational failure，不再能伪装成有效 0 分 aggregate；
planner 对 `local_holdout_gap_too_high` 也会生成 guarded no-external closed-loop repair
命令，而不是继续给 audit-only 路由。

随后按该路由复核 xsv：Docker Desktop service 起初未运行，`dockerDesktopLinuxEngine`
pipe 不存在；启动 `com.docker.service` 和 Docker Desktop 后，本地 cleanroom 闭环可执行。
`restore_patch5`/`restore_patch6` 只基于公开本地 exploration failure 调整 `frequency`
equal-count ordering，但复跑显示同一公开轴的 reference 顺序不稳定：`restore_patch5`
最终仍为 exploration `100/102`、holdout `12/15`，`restore_patch6` 同样没有改善。
generalization audit 继续判定 `risk_level=high`、`risk_reason=local_holdout_gap_too_high`，
strict official-ready ranker 在 `--max-local-holdout-gap 0.15` 下仍为 `row_count=0`。
因此本轮没有运行 ProgramBench official eval，也不能声明官方 aggregate breakthrough；
当前最重要的结论是继续把 xsv 归为本地泛化缺口，而不是重复提交官方评测。

此前重要增量：2026-05-21 继续按 no-external `file_bridge` 路径推进
`rbakbashev__elfcat.52f8cc7` 的 `reference_html_patch3`。本轮没有使用
Kimi/GLM/外部 LLM；仍由 ReBuilder 本地 file-bridge/subagent 架构完成推理。
patch3 不改变 patch2 的 HTML 兼容行为，只把 ELF64 program/section header 记录在
`render_html` 中预解析一次，并传给 byte spans、info tables、arrow connects，避免
官方 hidden eval 中重复解析造成额外性能风险；同时把 patch3 official wrapper 的
ProgramBench eval 超时提高到 `3600` 秒，Docker command timeout 提高到 `300` 秒。
验证结果：`py_compile` 通过，`python -m ruff check --no-cache ...` 通过，提升权限
focused pytest `tests\test_elfcat_file_bridge_harness.py` 为 `11 passed`；本地
no-external 闭环仍为 exploration `119/119`、holdout `17/18`、runtime smoke 覆盖
`args/default/input_files/stdin`。随后运行 ProgramBench official eval：
`runs\programbench_official_eval\submission_elfcat_reference_html_patch3_20260521`
生成 submission，但 official hidden pytest 运行约 `47:51` 后首轮 branch 为
`results_read_failed`，重试启动容器时 Docker Desktop Linux engine pipe
`npipe:////./pipe/dockerDesktopLinuxEngine` 不可用，ProgramBench summary 返回
`ERROR: RuntimeError`、`raw=0/0 score=0`、`counted=0/0 score=0`，且没有写出
`.eval.json`。父进程退出后遗留的高 CPU `programbench-e32a14c79e32` 容器已手动
停止。因此 patch3 只能作为本地性能风险修复和 official-eval operational failure
证据，不能作为官方 aggregate breakthrough；当时 elfcat recorded baseline 仍是
counted `316/564`、score `56`，后续 2026-05-22 `reference_html_patch4` 已把
当前记录 baseline 升到 score `66`。修复与困难记录已写入
`docs\public-release-materials.md` 的
`2026-05-21 Elfcat Reference HTML Patch3 Official Eval Error` 小节。
随后补修了 closed-loop official runner：`scripts\run_official_closed_loop.py`
现在会把“ProgramBench 命令返回但缺少 `.eval.json`”判定为 official-eval
operational failure，清理匹配的 ProgramBench 容器/compiled image，写入
`official_eval_failure_report.json`，并抛出明确 `RuntimeError`，避免后续被误汇总为
`raw=0/0`、`counted=0/0` baseline。focused 回归验证：
`py_compile` 通过，`ruff` 通过，提升权限 pytest 4 个 runner 用例通过。
随后继续修复官方失败证据归因：`scripts\rank_programbench_candidates.py` 不再按
task id 从共享 official-eval root 挂接旧失败报告，只有报告位于当前候选 submission
root 下或报告 metadata 指回该 submission root 时才接受；同时把 embedded
`official_eval_summary` 中的 `invalid_eval_payload` / `0/0` 识别为
`official_eval_failed_without_eval_json`，而不是当作官方 0 分。复核后 strict
official-ready ranker 仍为 `row_count=0`；`elfcat patch3` 被正确归类为
official-eval operational failure，且 `official_eval_failure_report_path=null`，
不再误指向 patch2 报告。修复与困难记录已写入
`docs\public-release-materials.md` 的
`2026-05-21 Official Failure Attribution Repair` 小节。验证：`py_compile` 通过，
`ruff` 通过，提升权限 focused pytest：ranker `70 passed`、planner `16 passed`。

此前重要增量：2026-05-21 修复 planner 对本地泛化缺口的误导性路由。本轮没有
调用 Kimi/GLM/外部 LLM，也没有运行 ProgramBench official eval；只做 ReBuilder
框架内的 no-external gate/audit 修复。`scripts\plan_official_breakthrough_targets.py`
现在会把本地 holdout 未改善、local-vs-holdout gap 过大、runtime-smoke 维度不足等
aggregate blocker 路由为 `target_class=local_generalization_gap`，
`next_action=repair_local_generalization_before_official_eval`，而不是继续显示为
`ready_baseline_gate`。`scripts\audit_generalization_risk.py` 新增可重复 `--task`
过滤，方便对单个 official-standard 候选做 aggregate-only 复核。

真实 `runs` 复核里，`burntsushi__xsv.f430466` 的 `restore_patch2` 已从
`ready_baseline_gate` 改为 `local_generalization_gap`，reason 为
`local_holdout_gap_too_high`；task-scoped risk audit 显示 local `0.9706`、holdout
`0.8000`、gap `0.1706`、`risk_level=high`、`block_official_eval=true`。这确认
本轮仍不能提交或宣称 official breakthrough。验证：`py_compile` 通过，
`python -m ruff check --no-cache ...` 通过，提升权限 focused pytest
`tests\test_plan_official_breakthrough_targets.py tests\test_audit_generalization_risk.py`
为 `23 passed`。普通 sandbox pytest 仍被
`C:\Users\Administrator\.codex-tmp\pytest-of-Administrator` ACL 拒绝，这是环境限制。
修复与困难记录已写入 `docs\public-release-materials.md` 的
`2026-05-21 Planner Local-Generalization Routing Repair` 小节。

此前重要增量：2026-05-21 继续按 no-external `file_bridge` 路径复核
`burntsushi__xsv.f430466` 的 `restore_patch2`。本轮仍没有使用 Kimi/GLM/外部
LLM；ReBuilder 通过本地 `file_bridge` 请求/响应完成推理。修复集中在本地可见的
subcommand help/usage 兼容层：从本地 reference evidence 恢复覆盖到的
`xsv <subcommand> --help` 完整文本，补齐 `partition` 和 `sample` 参数不足 usage
诊断，并尝试收窄 `stats --everything` 浮点展示差异。`frequency` 同频排序的
first-seen 尝试被回滚，因为它修复一个可见形状但回退另一个可见形状，说明该轴不能
作为稳定泛化规则。随后 `stats --everything` 的 float sum/mean 改成显式左到右流式
累加，修掉此前 `84.8` vs `84.80000000000001` 的可见差异。focused harness
提升权限后 `6 passed`，ruff 与 py_compile 通过；
最终 no-external 本地闭环为 exploration `99/102`、holdout `12/15`、runtime smoke
覆盖 `args/default/input_files/stdin`，submission 已生成。但
`audit_official_eval_gate.py` 返回 `eligible=false`、reason
`missing_official_candidate_summary`，严格 official-ready ranker 仍为 `row_count=0`，
所以本轮没有跑 ProgramBench official eval，也不能称为官方突破。剩余 visible gap
集中在 `xsv frequency` 的同频项顺序；同一 stdin 的本地 reference evidence 已出现
多个 tie order，因此本轮没有用 evidence 查表或随机化输出去伪造 100%。修复与困难记录已写入
`docs\public-release-materials.md` 的
`2026-05-21 Xsv Restore Patch2 Local Gate Follow-Up` 小节。

此前重要增量：2026-05-21 继续按 no-external `file_bridge` 路径推进
`rbakbashev__elfcat.52f8cc7` 的 `reference_html_patch2`。本轮没有使用
Kimi/GLM/外部 LLM；ReBuilder 仍通过本地 `file_bridge` 请求/响应完成推理。修复集中在
reference HTML 兼容层：Linux ABI/版本行、backslash path 与 directory 诊断、Rust panic
shape、ELF64 section header/program header 的 byte spans/info tables/arrow connects、exact
tail-row newline，以及 section-name table 的 O(n^2) 缓存风险。focused harness
`11 passed`，ruff 与 py_compile 通过；本地 official-standard visible set 达到
exploration `119/119`、holdout `17/18`、runtime smoke 覆盖
`args/default/input_files/stdin`，submission 已生成。但 ProgramBench official aggregate
eval 对
`runs\programbench_official_eval\submission_elfcat_reference_html_patch2_20260521`
连续两次在 `1200` 秒超时，均未写出 `eval.json`，最新失败报告为
`runs\programbench_official_eval\submission_elfcat_reference_html_patch2_20260521\official_eval_failure_report.json`。
所以当前只能说“本地可见官方样例 100%”，不能说官方 aggregate breakthrough；elfcat
recorded baseline 仍是 counted `316/564`、score `56`。修复与困难记录已写入
`docs\public-release-materials.md` 的
`2026-05-21 Elfcat Reference HTML Patch2 Official-Standard Attempt` 小节。

此前重要增量：2026-05-21 继续按 no-external `file_bridge` 路径复核
`burntsushi__xsv.f430466` 与 `chmln__sd.87d1ba5`。`xsv restore_patch2` 修复
frequency tie ordering 和空 `xsv index` 诊断，本地 ReBuilder 结果为 exploration
`83/102`、holdout `12/15`、runtime smoke 覆盖 `args/default/input_files/stdin`，
但 holdout 未超过历史 best，strict official-ready gate 仍为 `row_count=0`，因此未进
official eval。`chmln baseline_regex_patch1` 从已记录 score-86 baseline submission
恢复实现，修复 unclosed-group Rust regex diagnostic，并修掉 bridge runner 读取 CRLF
tarball 后在 Windows 写成 `0D 0D 0A` 的换行膨胀问题；复跑本地闭环为 exploration
`40/40`、holdout `12/12`、runtime smoke 覆盖 `args/default/input_files/stdin`。随后
完成 ProgramBench official eval：counted `699/810`、score `86`，raw `752/869`、
score `87`，比上一条 no-external score-86 记录多 2 个 counted tests，但 rounded
official score 未提升，`fully_resolved=false`。两项记录均写入
`docs\public-release-materials.md`，本轮没有使用 Kimi/GLM，也没有声明新的官方 score
突破。

此前重要增量：2026-05-20 的 `zip-password-finder` usage_patch2 follow-up 通过
ReBuilder `file_bridge` 路径完成，无外部 LLM/Kimi，官方 aggregate 从 score 36
升级到 score 40（counted `274/680`，raw `366/792`），但仍不是 solved task。对应
基线已记录在
`baselines\programbench\agourlay__zip-password-finder.704700d.baseline.json`；修复与困难记录见
`docs\public-release-materials.md` 的
`2026-05-20 Zip Password Finder Usage Patch2 Official Baseline Upgrade` 小节。此前同日
`go-mod-outdated` table_patch5 也完成了官方 aggregate baseline upgrade：score 80 到
score 94；`csview` axis-ablation contractfix 完成 score 57 到 score 87，均不是
solved task。随后针对 `chroma` 做了 no-external `file_bridge` generalization-probe
follow-up：本地 gate 提升到 probes `102`、holdout `46/46`、runtime smoke 覆盖
`args/default/input_files/stdin`，但官方 ProgramBench aggregate eval 在 3600 秒后超时且未
写出 `eval.json`。失败报告已记录在
`runs\file_bridge_no_external_chroma_20260520_restore_patch2_generalization_probe_submission\file_bridge_no_external_chroma_20260520_restore_patch2_generalization_probe_eval\official_eval_failure_report.json`；
这不是官方分数突破，修复与困难记录见
`docs\public-release-materials.md` 的
`2026-05-20 Chroma Generalization Probe Official Attempt` 小节。随后
`rank_programbench_candidates.py` 与 `plan_official_breakthrough_targets.py` 已补齐
failure-report 识别：该候选现在归类为 `official_eval_operational_failure` /
`official_eval_failed_without_eval_json`，不会再被误认为缺官方 summary 的 ready
candidate。随后继续复核 `clog-tool__clog-cli.7066cba` patch6：no-external
`file_bridge` 本地闭环达到 exploration `106/106`、holdout `16/16`，但官方
ProgramBench aggregate 仍为 counted `260/575`、score `45`，raw `394/778`、
score `51`，与既有 baseline 持平，不是突破；记录见
`2026-05-20 Clog Patch6 Official Same-Score Negative Evidence` 小节。

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

## 2026-05-15 架构优化尝试记录

本轮目标是争取新的 ProgramBench 官方 aggregate 小突破，但所有候选都严格保留 80% internal holdout gate；未过 gate 的候选没有触发官方评测，也没有更新 baseline。

已落地的通用改动：

- ProgramBench cleanroom 文档发现抽成统一模块，支持 `README.mkd`、`ADVANCED.mkd` 等 `.mkd`/多文档合并；`gron` workspace 文档长度由 0 变为 8858。
- 增强 adaptive probes 和 task profile：`find_replace`、`json_transform`、`html_selector`、`csv_table`、`archive_compression` 均补了更贴近文档/黑盒行为的轴。
- differential suite 会过滤 LLM 生成的 unsafe `input_files` 路径，例如 `/tmp/...`，避免无效探针在 validation 阶段中断整轮。
- 全量测试通过：`619 passed`。
- implementation 阶段新增 Python runtime smoke gate：生成后先做 AST integrity，再实际运行入口的 `<no args>`、`--help` 和最多 6 个安全 behavior-contract CLI 形态；若出现 Python traceback、执行异常或 timeout，会把 `runtime_smoke_*` issue 回传给 retry prompt。staged support module 若引入运行时崩溃，会被拒绝并回退到 entrypoint 版本，避免明显坏候选进入 full differential/holdout。
- task profile prompt 新增动态预算控制：正常内置 profile 保持完整；当 profile payload 过大时，自动裁剪 domains、hints、strategy playbook、anti-patterns 和 evidence keywords，并用 `__truncated__` 标记，避免 profile/probe 继续膨胀导致 implementation prompt 失控。
- 本轮机制优化验证：先用新增 TDD 用例确认 contract-only dispatch 崩溃和超大 TaskProfile 会穿透旧逻辑，再实现后通过聚焦 ruff、prompt/repair/smoke 相关测试和全量测试；当前 `.venv` 下 `pytest -q` 为 `626 passed`，系统 Python 3.14 不作为基线。
- 候选排名/官方准入审计新增显式 baseline upgrade 模式：默认仍把已有官方 eval/baseline 的任务标为 `already_official`；只有加 `--allow-existing-official` 时，已过本地 aggregate gate 的既有任务才会显示为 `eligible_baseline_upgrade`。这用于“小幅升级已有官方分数”的审计路径，不会读取或回灌官方隐藏失败。
- 真实 runs 复核：普通 `--official-eligible-only --latest-per-task` 仍为空；`--allow-existing-official` 可显示 `clog-cli` 与 `nnn` 当前 baseline 级候选，但再叠加 `--require-holdout-improvement --min-holdout-improvement-delta 0.02` 后仍为空。因此当前还没有新的可提交官方评测候选。
- 尝试执行推荐的 `hexyl` local-only rerun 时，外部安全审查阻止了 `--execute`，原因是该流程会把本地提示/代码上下文发送给外部 LLM 服务并写 run 产物；本轮没有绕过该限制，也没有触发官方评测。
- 新增 `scripts/audit_official_baseline_candidates.py`，用于只读比较已有 `*.eval.json` 官方 aggregate 结果和 `baselines/programbench` 记录。它发现并补记了两个历史低样本官方非零 baseline：`rbakbashev__elfcat.52f8cc7` score 17（96/564 counted，本地 holdout 只有 2 cases）和 `alecthomas__chroma.8d04def` score 3（13/515 counted，本地 holdout 只有 5 cases）。补记后 actionable 审计表为空；这些记录是历史 aggregate 证据，不是当前 80% gate 下的新提交候选。
- 新增 `scripts/plan_official_breakthrough_targets.py`，把 recorded official baseline aggregate 分数与本地 latest/best reliable holdout trend 合并，输出 cleanroom-safe 的官方突破目标队列。当时真实 runs 优先级为：`clog-cli`、`nnn` 属于 `ready_baseline_gate`；`htmlq`、`go-mod-outdated`、`gron`、`zip-password-finder`、`xsv`、`csview`、`cmatrix` 属于 `restore_historical_gate`；`zoxide` 属于 `weak_cleanroom_rerun`；`chroma`、`elfcat` 只有历史低样本官方 baseline 且缺可靠 holdout。后续 `elfcat` 已补可靠 holdout，并经过 no-external `file_bridge` 迭代把官方 aggregate baseline 升到 score 66；该脚本仍只读 baseline 的 official score/counts 与 `result.json` 的 holdout aggregate，不读取 hidden/detail failure。
- `plan_official_breakthrough_targets.py --include-next-command` 已补齐 restore 行命令：对历史 best `result.json` 生成 `audit_official_eval_gate.py ... --allow-existing-official`，用于确认旧 best 仍是本地 aggregate baseline-upgrade 候选。已实际审计 `htmlq`、`gron`、`xsv`、`zip-password-finder` 的历史 best，均返回 `eligible_baseline_upgrade`；这说明下一步重点应是恢复/ablate 历史 best 机制，而不是提交最新退化 run。
- `plan_official_breakthrough_targets.py` 新增 `--include-restore-ablation-command`，可把 restore 行的 next command 从历史 best 审计切换为 guarded `run_official_strategy_ablation.py --dry-run`。真实 runs 下已输出 `htmlq`、`go-mod-outdated`、`gron`、`zip-password-finder`、`xsv`、`csview`、`cmatrix` 的 dry-run ablation 命令，均带 `--skip-official-eval`、`--require-holdout-improvement`、`--holdout-history-root runs`、`--max-generalization-risk low` 和 smoke-axis gate。
- 新增 `scripts/run_restore_axis_ablation_batch.py`，作为 restore-axis 批量入口。它只选择 aggregate-only planner 中的 `restore_historical_gate` 行，默认只打印 guarded strategy ablation 命令；只有显式 `--execute` 才会调用子进程。真实 runs 下 dry-run smoke 已输出 7 个 restore 目标命令，未执行外部 LLM、Docker 或 official eval。
- 新增 `scripts/audit_restore_targets.py`，专门审计 `restore_historical_gate` 子集。它只输出 official aggregate baseline、latest/best reliable holdout、best/latest gate reason、axis count、regression signal 和 result paths。真实 runs 下：`htmlq` 回退 -47.2%、`gron` 回退 -43.8%、`zip-password-finder` 回退 -75.0%、`xsv` 回退 -81.8%，且这些任务的 latest axes 均从历史 best 的 `0/0` 增加到非零，因此被标为 `new_axis_expansion_regression`。这支持下一步先做新增 probe/strategy axis 的 ablation。
- 新增 `scripts/audit_generalization_risk.py`，作为 official eval 前的 aggregate-only 反过拟合 gate。当时真实 runs 使用 `--fail-on-risk high` 时会阻断：缺可靠 holdout 的 `chroma/elfcat`、低于 gate 的 `zoxide`、latest 退化的 restore 任务，以及 `htmlq/gron/zip-password-finder/xsv` 这类 `new_axis_expansion_regression`。后续 `elfcat` 已补可靠 holdout 并完成官方 aggregate eval；`chroma` 仍因无 eval JSON 不能声明官方分数。`clog-cli/nnn` 当时为 low risk，但也只是允许进入 baseline-upgrade/holdout-improvement 审计，不代表直接官方提交。
- `package_submission.py`、`run_official_closed_loop.py` 和 `run_official_strategy_ablation.py` 已支持 `--max-generalization-risk low|medium|high`，并透传 `--generalization-risk-root`、`--baseline-root`、`--official-eval-root`。闭环 runner 与 strategy ablation 现在可在 package/official eval 前强制执行 aggregate-only 反过拟合门禁；已用 htmlq 高风险候选 smoke 验证会因 `new_axis_expansion_regression` 阻断。
- task-domain strategy skills 已统一升级：`core/profiling/rules/*.yaml` 的 11 个领域 pack 全部新增 `generalization_playbook`，覆盖 unseen holdout、CLI dispatch、stdin/file、error branch、bounded smoke 等通用泛化检查；`TaskProfile` 类型、profile loader、implementation/repair prompt 均已接入该字段。该字段只来自 cleanroom docs/probes 的领域规则，不使用 official hidden failure。
- adaptive deterministic probes 已补齐到全部 11 个 strategy domains：此前已有 network/csv/json/html/archive/go/binary/find_replace，现在新增 `terminal_ui`、`filesystem_tool`、`terminal_animation` 的本地 smoke axes。真实代码统计为 network 9、csv 11、json 10、html 17、archive 8、terminal_ui 6、go 6、filesystem 7、terminal_animation 7、binary 6、find_replace 9。
- 新增 `scripts/audit_strategy_domain_coverage.py --fail-on-missing`，把 profile rule、`generalization_playbook`、adaptive smoke/adaptive axes 绑定成可执行本地 gate。当前 11 个 domain 均为 `ok`，该审计不读取 holdout/official hidden failure。
- repair 阶段已接入 implementation 阶段同源的 Python integrity/runtime smoke gate。每次 repair 生成候选后，若出现语法错误、缺 entrypoint、entrypoint 不 dispatch、缺 import 或 runtime smoke traceback，会立即把该 repair 记录为 `repair_integrity_failed` 并恢复上一版 accepted codebase，避免 xsv 这类 0% syntax-broken 修复被 accepted。
- 11 个 task-domain strategy skills 已进一步补齐 `validation_playbook`：每个 domain 都声明 3 条 cleanroom-local 验证清单，用于 smoke、holdout 维度拆分和非回归检查；`TaskProfile`、prompt 注入和 `audit_strategy_domain_coverage.py --fail-on-missing` 均已接入。该清单只描述通用验证类别，不包含官方 hidden failure 或任务答案表。
- `audit_strategy_domain_coverage.py --fail-on-missing` 现在同时做 strategy skill cleanroom-policy lint：若 domain pack 出现 `official`、hidden-test 细节、test-set/leaderboard/eval score 语汇或具体 ProgramBench task id，会把该 domain 标为 `missing_cleanroom_policy` 并失败。当前 11 个 domain 的 cleanroom issues 均为 0。
- `docs/programbench-cleanroom-goal-audit.md` 已新增 2026-05-16 active goal audit addendum：按“官方突破、反过拟合、外部泛化、可执行验证”拆成 completion checklist，并用 fresh 命令确认严格 official-eligible 表仍为空、generalization risk 仍有 high 阻断、11 个 strategy skills cleanroom gate 全绿、全量 `.venv` pytest 为 `664 passed`。因此 active goal 仍不能标记完成。
- `run_official_strategy_ablation.py` 新增 `--dry-run`：可为 restore-axis 目标打印每个 variant 的 child `run_official_closed_loop.py` 命令，而不调用外部 LLM、Docker、packaging 或 official eval。已对 `htmlq`、`gron`、`xsv`、`zip-password-finder` 生成过 dry-run 命令，命令固定保留 `--skip-official-eval`、`--require-holdout-improvement`、`--max-generalization-risk low` 和 smoke-axis gate。本轮又用 `htmlq` 的 `baseline_no_adaptive/adaptive_profile` 做了 fresh dry-run smoke，exit 0，且只打印 child 命令。实际执行这些 ablation 前仍需要显式授权外部 LLM/Docker。
- holdout improvement gate 已支持公平排除当前实验根目录：`audit_holdout_improvement.py` 新增 `--exclude-root`，`run_official_closed_loop.py` 新增 `--holdout-history-exclude-root`，strategy ablation runner 会自动把父 `--runs` 目录传给每个 child。这样 `--holdout-history-root runs` 可继续使用历史 aggregate 结果，但不会让同一批 in-flight variants 互相成为 previous best。已用 `htmlq` dry-run smoke 复核 child 命令包含 `--holdout-history-exclude-root runs\restore_axis_ablation_dryrun\htmlq`，未执行外部流程。
- 已批量执行 7 个 restore 目标的 strategy ablation dry-run：`htmlq`、`go-mod-outdated`、`gron`、`zip-password-finder`、`xsv`、`csview`、`cmatrix` 均 exit 0。每个目标打印 `baseline_no_adaptive/adaptive_profile/adaptive_deep` 三个 child closed-loop 命令，命令均包含 `--skip-official-eval`、`--require-holdout-improvement`、`--holdout-history-exclude-root runs\restore_axis_ablation_dryrun\<task>`、`--max-generalization-risk low` 和 `--min-smoke-contract-axes 1`。
- 外部执行确认门已补齐到直接入口：`run_official_closed_loop.py` 现在没有 `--ack-external-llm-docker` 会在加载样本和运行子命令前退出；非 dry-run 的 `run_official_strategy_ablation.py` 也要求同一确认并把确认传给 child closed-loop。`run_restore_axis_ablation_batch.py` 与 `run_weak_task_cleanroom_rerun.py` 在 `--execute --ack-external-llm-docker` 时会继续把确认传给子入口；`run_programbench_mini_lab.py` 也要求 ack 后才加载 catalog/准备任务/调用 ReBuilder。缺少 ack 的 execute smoke 会提前退出。聚焦回归为 `tests/test_run_programbench_mini_lab_script.py`、`tests/test_run_official_strategy_ablation.py`、`tests/test_run_official_closed_loop.py`、`tests/test_run_restore_axis_ablation_batch.py`、`tests/test_run_weak_task_cleanroom_rerun.py` 共 122 passed，`python -m ruff check ...` 通过；本轮新增 planner/restore JSON dry-run command plan 后全量 `.venv` pytest 为 676 passed in 8.98s。
- `audit_restore_targets.py` 现在输出 cleanroom-local axis delta：从 `implementation_metadata.probe_axis_coverage` 的 `smoke_contract_axes` / `adaptive_axes` 读取并过滤 `domain.axis` 形式的本地轴名，新增 `added axes` / `removed axes` / `axis action` 列。真实 runs 复核显示：`htmlq` 建议 `ablate_added_axis_domains:html_selector`，`gron` 建议 `json_transform`，`zip-password-finder` 建议 `archive_compression,json_transform`，`xsv` 建议 `csv_table`；`go-mod-outdated`、`csview`、`cmatrix` 属于 same-axis regression，标记为 `inspect_same_axis_strategy_regression`。这给下一轮 restore/ablation 提供通用轴级入口，不使用 hidden failure。
- `audit_restore_targets.py` 新增 `--format json`，输出 `schema_version`、`row_count`、`total_row_count` 和每行 cleanroom-safe aggregate/axis/action payload，供后续 batch 或 dashboard 直接消费，避免解析 markdown 或展开原始 result/baseline 负载。真实 `runs` smoke：`--limit 2 --format json` 返回 `row_count=2`、`total_row_count=7`，首行 `htmlq` 的 `axis_delta_action` 为 `ablate_added_axis_domains:html_selector`，第二行 `go-mod-outdated` 为 `inspect_same_axis_strategy_regression`。
- `run_restore_axis_ablation_batch.py` 现在支持 `--axis-action-domain <domain>` 和 `--show-axis-action`。它会通过 aggregate restore audit 的 `axis_delta_action` 过滤目标，再打印同样带 `--skip-official-eval`、holdout improvement、generalization risk 和 smoke-axis gate 的 child dry-run 命令。真实 `runs` smoke：`--axis-action-domain csv_table --show-axis-action --limit 7` 只选中 `burntsushi__xsv.f430466`，并标注 `axis_action=ablate_added_axis_domains:csv_table`，未执行外部流程。
- `run_restore_axis_ablation_batch.py` 新增 `--format json`，用于输出 machine-readable dry-run command plan。JSON 模式只支持 dry-run 计划，非 dry-run execute 会返回错误，避免子进程日志与 JSON 混合。真实 `runs` smoke：`--axis-action-domain csv_table --show-axis-action --limit 7 --format json` 返回 `schema_version=1`、`execute=false`、`row_count=1`，唯一行是 `burntsushi__xsv.f430466`，command array 保留 `--skip-official-eval` 和 `--dry-run`。
- `plan_official_breakthrough_targets.py` 新增 `--format json`，将完整 official breakthrough target queue 输出为 aggregate-only JSON。真实 `runs` smoke：`--include-next-command --include-restore-ablation-command --limit 12 --format json` 返回 `schema_version=1`、`row_count=12`、`total_row_count=12`，覆盖 ready/restore/weak/missing-holdout 四类目标；`next_command` 只包含 guarded dry-run 或审计命令，不含 hidden failure 细节。
- 新增 `scripts/run_missing_holdout_cleanroom_rerun.py`，用于 `chroma`、`elfcat` 这类已有历史 official aggregate baseline 但当前缺可靠本地 holdout 的任务。该 wrapper 默认只 dry-run，child closed-loop 命令固定带 `--skip-official-eval`，不带 `--require-holdout-improvement`，因为还没有可靠 previous local holdout 可比较；真实执行仍需要 `--execute --ack-external-llm-docker`。
- `plan_official_breakthrough_targets.py` 新增 `--include-missing-holdout-command`、`--missing-holdout-rerun-root`、`--missing-holdout-min-smoke-contract-axes`。真实 `runs` smoke：`--include-next-command --include-missing-holdout-command --include-restore-ablation-command --limit 12 --format json` 返回 `row_count=12`，并为 `alecthomas__chroma.8d04def`、`rbakbashev__elfcat.52f8cc7` 输出 `run_missing_holdout_cleanroom_rerun.py ... --dry-run` 命令。
- `plan_official_breakthrough_targets.py` 现在还支持 ready-baseline strict command flags：`--baseline-upgrade-min-smoke-contract-axes`、`--baseline-upgrade-require-holdout-improvement`、`--baseline-upgrade-min-holdout-improvement-delta`。真实 `runs` smoke 加上这些 flags 后，`clog-cli` 与 `nnn` 的 `next_command` 会把 `rank_programbench_candidates.py` 命令收紧到 smoke-axis + holdout-improvement gate，避免 low-risk ready 行被误读成可直接官方提交。
- 本轮 focused verification：`tests/test_run_missing_holdout_cleanroom_rerun.py` 与 `tests/test_plan_official_breakthrough_targets.py` 合计 `14 passed`；`python -m ruff check` 已通过本轮 touched planner/wrapper 文件；全量 `.venv` pytest 为 `684 passed in 9.69s`。wrapper/planner dry-run smoke 只打印命令，未执行外部 LLM、Docker 或 official eval。
- `audit_generalization_risk.py` 新增 `--format json`，把反过拟合 gate 输出为 machine-readable aggregate-only payload。真实 `runs` smoke 返回 `schema_version=1`、`row_count=12`、`total_row_count=12`；`--fail-on-risk high --format json` 仍会非零退出并保留可解析 JSON，字段只包含官方 aggregate、target class、risk level/reason、本地 holdout aggregate、路径和 required next action，不展开 hidden failure 细节。
- 本轮 JSON 风险审计验证：`tests/test_audit_generalization_risk.py` 为 `4 passed`；`python -m ruff check scripts\audit_generalization_risk.py tests\test_audit_generalization_risk.py` 通过；严格 official-eligible 表仍为空，`audit_generalization_risk.py --fail-on-risk high` 仍阻断 high-risk 行，strategy domain coverage 11 个 domain 全部 `ok`，全量 `.venv` pytest 为 `685 passed in 9.34s`。没有触发外部 LLM、Docker 或 official eval。
- `audit_strategy_domain_coverage.py` 新增 `--format json`，把 11 个 strategy domain 的 generalization/validation/cleanroom/probe 覆盖状态输出为 machine-readable aggregate-only payload。真实 smoke 返回 `schema_version=1`、`row_count=11`、`total_row_count=11`，全部 domain 为 `ok`；JSON 不打印 markdown banner，也不输出 strategy pack 原文或 matched cleanroom-policy 片段。
- 本轮 strategy coverage JSON 验证：先用新增 CLI 测试确认缺 `--format json` 时失败，再实现后 `tests/test_audit_strategy_domain_coverage.py` 为 `4 passed`；`python -m ruff check scripts\audit_strategy_domain_coverage.py tests\test_audit_strategy_domain_coverage.py` 通过；全量 `.venv` pytest 为 `686 passed in 10.06s`。
- `rank_programbench_candidates.py` 新增 `--format json`，把 candidate ranking / strict official-eligible gate 输出为 aggregate-only JSON。真实 strict gate smoke 使用 `--official-eligible-only --latest-per-task --min-smoke-contract-axes 1 --require-holdout-improvement --min-holdout-improvement-delta 0.02 --format json` 返回 `row_count=0`、`total_row_count=0`、`rows=[]`；普通 `--latest-per-task --limit 3 --format json` 只输出 local/holdout aggregate、axis counts、gate reason、status、official marker 和 result path。
- 本轮 candidate-ranking JSON 验证：先用隐藏 marker 回归测试确认旧 CLI 因缺 `--format json` 失败，再实现后 `tests/test_rank_programbench_candidates.py` 为 `57 passed`；`python -m ruff check scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py` 通过；全量 `.venv` pytest 为 `687 passed in 9.60s`。
- `summarize_holdout_trends.py` 新增 `--format json`，把 latest-vs-best holdout trend 和 weak-task rerun recommendations 输出为 aggregate-only JSON。真实 smoke 用 `--recommend-weak-reruns --include-rerun-command --rerun-min-smoke-contract-axes 1 --rerun-min-holdout-improvement-delta 0.02 --format json` 返回 trend `row_count=3`/`total_row_count=13`，recommendation `row_count=3`/`total_row_count=4`；top dry-run 目标为 `hexyl`、`zoxide`、`pingu`，命令仍包含 `--dry-run`、smoke-axis gate 和 holdout-improvement delta gate。
- 本轮 weak-task trend JSON 验证：先用隐藏 marker 回归测试确认旧 CLI 因缺 `--format json` 失败，再实现后 `tests/test_summarize_holdout_trends.py` 为 `31 passed`；`python -m ruff check scripts\summarize_holdout_trends.py tests\test_summarize_holdout_trends.py` 通过；全量 `.venv` pytest 为 `688 passed in 9.69s`。
- 新增 `scripts/run_weak_task_cleanroom_rerun_batch.py`，批量消费 aggregate-only weak-task recommendations。默认只 dry-run，`--format json` 只输出命令计划；真实 `runs` smoke 返回 `row_count=3`，目标为 `hexyl`、`zoxide`、`pingu`，每条 child `run_weak_task_cleanroom_rerun.py` 命令都带 `--dry-run`、`--min-smoke-contract-axes 1`、`--min-holdout-improvement-delta 0.02`，未执行外部流程。
- 本轮 weak-task batch wrapper 验证：新增测试先因模块不存在失败，再实现后 `tests/test_run_weak_task_cleanroom_rerun_batch.py` 为 `7 passed`；`python -m ruff check scripts\run_weak_task_cleanroom_rerun_batch.py tests\test_run_weak_task_cleanroom_rerun_batch.py` 通过；全量 `.venv` pytest 为 `695 passed in 9.75s`。
- behavior contract 现在保留 cleanroom 观察里的安全相对 `input_files` 和 input previews；implementation prompt 会展示文件名与有界预览，Python runtime smoke 会把这些输入文件写入临时 workdir 后运行安全 contract CLI case。这样 implementation/repair 阶段不再只覆盖 `<no args>`、`--help`、stdin 形态，也能捕获 `csv/html/json/binary` 等文件模式的 entrypoint dispatch 崩溃。
- 本轮 file-input runtime smoke 验证：新增 TDD 测试先失败于 `BehaviorContract` 缺 `input_files` 字段、prompt 缺 input preview、runtime smoke 跳过文件参数 contract；实现后 focused `3 passed`，相关 `tests/test_spec_synthesizer_parsing.py tests/test_agent_output_parsing.py tests/test_codebase_integrity.py tests/test_repair_loop_parsing.py` 为 `75 passed`，`python -m ruff check` 通过 touched files，全量 `.venv` pytest 为 `696 passed in 10.23s`。
- spec synthesis 进一步过滤 unsafe input-file prompt 泄漏：`_format_corpus()` 现在只展示安全相对 input file 的名称和预览，丢弃 unsafe 路径及其内容；若 argv 中正好引用被丢弃的 unsafe input file，会 redacted 为 `<unsafe_input_file>`，避免无效本地路径进入 exact behavior contract。Python runtime smoke 也会跳过 `../...` 等 unsafe 文件路径 argv，即便该 contract 同时带了安全 input_files。
- 本轮 unsafe input-file 边界验证：新增测试先确认 unsafe 文件名/内容会出现在 spec prompt、unsafe argv 会被 runtime smoke 执行；实现后新增安全测试 `2 passed`，相关 spec/prompt/integrity 测试 `59 passed`，`python -m ruff check` 通过 touched files，全量 `.venv` pytest 为 `698 passed in 9.93s`。
- behavior contract 现在也保留安全 env vars：新增 `core/execution/env.py` 共享过滤器，只允许合法变量名、短值，并过滤 token/secret/password/key/credential/auth 等敏感名称。Spec prompt、implementation behavior contract prompt 和 Python runtime smoke 都只使用过滤后的 env vars，使 `TERM/COLUMNS/LINES/NO_COLOR` 这类 terminal UI/animation cleanroom probe 能进入实现阶段 smoke，而不会携带凭据。
- 本轮 env-var contract 验证：新增 TDD 测试先失败于 spec prompt 缺 env、behavior contract prompt 缺 env、runtime smoke 未传 `TERM=unknown`；敏感 `API_TOKEN` case 保持不触发。实现后 focused `4 passed`，相关 spec/prompt/integrity/execution-backend 测试 `81 passed`，`python -m ruff check` 通过 touched files，全量 `.venv` pytest 为 `702 passed in 9.98s`。
- runtime smoke 去重键已从 `args/stdin` 扩展为 `args/stdin/input file content fingerprints/env vars`。这修复了 terminal env-only contract 被默认 `<no args>` smoke case 吞掉的问题，也避免同 argv 但不同输入文件内容的 contract 被误判重复。
- 本轮 runtime smoke identity 验证：新增 TDD 测试先确认 `TERM=unknown` 且空 argv/stdin 的 contract 会被旧去重跳过；实现后该测试通过，相关 spec/prompt/integrity 测试 `64 passed`，`python -m ruff check core\codebase\runtime_smoke.py tests\test_codebase_integrity.py` 通过，全量 `.venv` pytest 为 `703 passed in 10.13s`。
- spec synthesis 现在会 redacted 原始 argv 中的 unsafe file-like path，即使该路径没有出现在 `input_files` map 中。覆盖对象包括绝对路径、Windows drive-qualified path 和 parent traversal path；URL 形态不作为文件路径处理。这样无效本地路径不会进入 observation prompt 或 exact behavior contract args。
- 本轮 raw argv redaction 验证：新增 TDD 测试先确认 `C:\Users\Administrator\secret.txt` 会进入 prompt/contract args；实现后相关 spec/prompt/integrity 测试 `65 passed`，`python -m ruff check core\spec_synthesizer.py tests\test_spec_synthesizer_parsing.py` 通过，全量 `.venv` pytest 为 `704 passed in 9.93s`。
- Python runtime smoke 现在会输出 aggregate-only 的 `generation_metadata["runtime_smoke"]`：记录 implementation smoke 实际执行的 case 数、contract case 数和输入维度（args/stdin/input_files/env_vars/default），但不记录 argv 值、文件内容、stdout/stderr、holdout failure 或 official hidden detail。`PythonRuntimeSmokeChecker.check()` 返回 report，原 `find_issues()` API 保持兼容，`ImplementerAgent` 在生成成功路径记录该元数据。
- 本轮 runtime-smoke metadata 验证：新增 TDD 测试先失败于缺少 `generation_metadata["runtime_smoke"]`；实现后 focused 测试通过，相关 implementer/integrity 测试 `55 passed`，`python -m ruff check core\codebase\runtime_smoke.py core\implementer_agent.py tests\test_agent_output_parsing.py` 通过，全量 `.venv` pytest 为 `705 passed in 10.05s`。严格 official-eligible JSON gate 仍为 `row_count=0`、`total_row_count=0`，未触发外部 LLM、Docker 或 official eval。
- `rank_programbench_candidates.py` 现在新增可选 `--require-runtime-smoke-dimensions` gate。该 gate 会要求 candidate 的 `implementation_metadata.runtime_smoke.status == "passed"`，且实际 smoke 输入维度包含所请求的 aggregate 维度（如 `args,input_files,env_vars`），否则 official gate reason 为 `runtime_smoke_not_passed` 或 `insufficient_runtime_smoke_dimensions`。默认关闭；JSON/markdown 只输出 status、case counts 和 dimension names，不输出 argv、文件内容、stdout/stderr、holdout failure 或 official hidden detail。
- 本轮 runtime-smoke dimension gate 验证：新增 TDD 测试先失败于 `collect_candidates()` 缺 `required_runtime_smoke_dimensions` 参数；实现后 `tests/test_rank_programbench_candidates.py` 为 `58 passed`，`python -m ruff check scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py` 通过。真实 strict gate 加 `--require-runtime-smoke-dimensions args,input_files` 仍返回 `row_count=0`、`total_row_count=0`；全量 `.venv` pytest 为 `706 passed in 10.17s`。未触发外部 LLM、Docker 或 official eval。
- `plan_official_breakthrough_targets.py` 新增 `--baseline-upgrade-require-runtime-smoke-dimensions`，只把该要求传入 ready-baseline 的 `rank_programbench_candidates.py` next command。这样 planner dry-run 输出和最终 official-eligible local gate 保持一致，同时 restore/weak/missing-holdout 行仍是 guarded dry-run。
- 本轮 planner pass-through 验证：新增测试先失败于 argparse 不识别该 flag；实现后 focused 测试通过，`tests/test_plan_official_breakthrough_targets.py` 为 `8 passed`，`python -m ruff check scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py` 通过。真实 planner JSON dry-run 加 `--baseline-upgrade-require-runtime-smoke-dimensions args,input_files` 输出 `row_count=12`、`total_row_count=12`，ready-baseline next command 包含 `--require-runtime-smoke-dimensions 'args,input_files'`；全量 `.venv` pytest 为 `706 passed in 10.33s`。未触发外部 LLM、Docker 或 official eval。
- packaging/closed-loop 本地 gate 现在也能要求 runtime-smoke 输入维度：`SubmissionHoldoutGate`、`package_submission.py`、`run_official_closed_loop.py` 接入同一个 aggregate `--require-runtime-smoke-dimensions args,input_files` 语义；direct closed-loop 会在 packaging/official eval 前检查 `runtime_smoke.status == "passed"` 和所需维度。
- 本轮 closed-loop gate 验证：新增测试先失败于 `SubmissionHoldoutGate` 构造参数缺失、`package_submission.py`/`run_official_closed_loop.py` 不识别 flag、child command 未透传；实现后新增 focused `5 passed`，相关 packaging/closed-loop/wrapper 测试 `173 passed`，`python -m ruff check` 通过 touched Python 文件。真实 dry-run 验证 strategy ablation、weak-task、missing-holdout、restore-batch JSON、weak-batch JSON 命令均包含 `--require-runtime-smoke-dimensions args,input_files`。全量 `.venv` pytest 为 `715 passed in 10.74s`，strict official-eligible JSON gate 仍为 `row_count=0`、`total_row_count=0`。未触发外部 LLM、Docker 或 official eval。
- 尝试执行 `sharkdp__hexyl.2e26437` 的 external-LLM weak-task cleanroom rerun（仍跳过官方评测）被环境策略拒绝：原因是会把 task/code context 发送到外部 LLM 服务。不要绕过该拒绝；后续除非策略允许更安全的外部执行路径，否则只能继续本地 aggregate audit、dry-run planning 和框架硬化。
- `rank_programbench_candidates.py` JSON 现在保留原 `official_gate` 第一个原因，同时新增 `official_gate_blockers` 列出所有 aggregate blockers，避免 runtime-smoke metadata 缺失被 low holdout / too few cases / already official 等早期原因遮住。新增 TDD 测试先失败于缺少 `official_gate_blockers`，实现后 focused `2 passed`，完整 `tests/test_rank_programbench_candidates.py` 为 `59 passed`，`python -m ruff check scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py` 通过。真实 latest-per-task JSON smoke 输出 `row_count=23`、`total_row_count=23`，blocker counts 包括 `runtime_smoke_not_passed=23`、`low_holdout_rate=17`、`insufficient_smoke_contract_axes=17`、`already_official=12`、`too_few_holdout_cases=10`。
- `scripts/audit_runtime_smoke_replay.py` 新增为历史候选 runtime-smoke replay readiness 审计入口。默认只读扫描 `runs/**/result.json`，从邻近 `evidence/` store 重建安全 behavior contracts，并输出 aggregate-only JSON/markdown；`--execute` 只在本地运行生成 Python 文件的 bounded runtime smoke，不调用外部 LLM、Docker、packaging 或 official eval。真实 `runs` 复核：只读模式在 `--require-runtime-smoke-dimensions args,input_files` 下统计出 96 个 `insufficient_contract_artifacts`、16 个 `ready_for_replay`、4 个 `missing_entrypoint`；本地 execute 模式为 14 个 `replay_passed`、2 个 `replay_failed`、96 个 `insufficient_contract_artifacts`、4 个 `missing_entrypoint`，两个失败分别是 `chmln__sd.87d1ba5` 的 `runtime_smoke_traceback` 和 `sheepla__pingu.926d475` 的 `runtime_smoke_timeout`。本轮新增测试 `4 passed`，相关 runtime-smoke/official-gate 回归 `111 passed`，ruff passed，最新全量 `.venv` pytest 为 `722 passed in 12.29s`；这增强了本地验证证据，但不是官方突破证据。
- `scripts/audit_runtime_smoke_gate_replay.py` 新增为 strict official gate 与 runtime-smoke replay 的交叉审计入口。它复用 candidate gate blockers 和本地 replay 结果，不修改历史 `result.json`，只输出 aggregate 状态、blocker、维度和路径。真实 `runs` 严格参数（latest-per-task、smoke-axis、`args,input_files` runtime-smoke、holdout improvement delta 0.02、`--execute-replay`）下得到 23 行：0 个 `metadata_only_runtime_smoke_blocker`、6 个 `replay_resolved_but_other_blockers_remain`、17 个 `replay_failed_or_incomplete`。结论是 strict gate 为空不是单纯 runtime-smoke metadata 缺失导致，剩余阻断仍是低 holdout、未改善、case 不足、smoke-axis 不足和已有 official/baseline 状态。新增测试 `3 passed`，ruff passed；JSON 不输出 argv、输入文件内容、stdout/stderr、holdout failure 或 official hidden 细节。
- `.env` 已确认存在且仅包含 `GLM_API_KEY`、`KIMI_API_KEY` 两类外部 LLM key；`llm_clients/factory.py` 会从项目 `.env` 解析这些变量。按用户要求发起一次 `sharkdp__hexyl.2e26437` GLM cleanroom rerun 审批（官方评测仍禁用），但环境策略拒绝，因为会把 task/code context 发送到外部 LLM 服务。不要绕过该拒绝；如需真实 LLM 评测，只能由用户在本机 PowerShell 手动运行同一 guarded command，或切换到本地 LLM endpoint/获得策略层允许。
- 新增 `local_openai` LLM provider：支持 Ollama/LM Studio/vLLM 等 OpenAI-compatible `/chat/completions` loopback endpoint，默认拒绝非 loopback host，API key 可为空，仅在本地 gateway 需要 bearer auth 时使用 `LOCAL_OPENAI_API_KEY`。已接入 `main.py --provider local_openai`、`llm_clients/factory.py`、`config/settings.yaml` 和 `config/smoke_glm.yaml`，用于外部 GLM/Kimi 出口被策略阻止时继续做真实本地 LLM cleanroom rerun。
- 2026-05-17 工作区整理补记 `chmln__sd.87d1ba5` 官方 aggregate baseline：score 86（`695/810` counted；raw `749/869`）来自 `runs\programbench_official_eval\submission_chmln_sd_87d1ba5`。本地 run 为 `runs\weak_task_cleanroom_rerun\chmln__sd.87d1ba5_wsl_exec_fullcatalog\...result.json`，holdout `13/14`，runtime smoke passed，输入维度覆盖 args/stdin/input_files/default。baseline 已写入 `baselines\programbench\chmln__sd.87d1ba5.baseline.json`；该结果仍是 aggregate baseline，不是 fully resolved，也没有使用 hidden 失败细节。
- 2026-05-18 按“官方测试集验证阶段不使用外部 LLM”的边界，用 Codex 子代理经 `file_bridge` 跑通 `chmln__sd.87d1ba5` closed loop 并执行官方 ProgramBench eval。ReBuilder 本地结果为 exploration `47/49`、holdout `14/14`、runtime smoke passed；官方 aggregate 为 score `86`（`697/810` counted；raw `750/869`）。这比 2026-05-17 baseline 多过 2 个 counted tests，但 score 仍为 `86`，`fully_resolved=false`、`almost_resolved=false`，因此不是新的 score 档突破或 solved 任务。
- 2026-05-18 针对 solved-task 方向继续攻坚 `abishekvashok__cmatrix.5c082c6`：先用 no-external-LLM file_bridge 子代理候选取得本地 replay 全绿但官方退回 score `82`；随后改从历史 best adaptive_profile 出发，只用 cleanroom-local failures 修补 `-n`/`--`/`-u abc`/`/dev/pts/*` 行为，post-patch replay 为 exploration `64/64`、holdout `16/16`。官方 aggregate 提升到 score `95`（`481/508` counted；raw `739/769`），baseline 已更新；`fully_resolved=false`、counted `almost_resolved=false`，所以这是 score 档突破但还不是 solved-task。
- 2026-05-17 本轮继续按“官方测试集验证不使用外部 LLM”的边界整理审计入口：`summarize_holdout_trends.py`、`audit_runtime_smoke_replay.py`、`audit_runtime_smoke_gate_replay.py` 均已支持可重复 `--task <task_id>` 精确过滤，方便单任务复核而不用全量扫 `runs`。focused tests：`tests/test_summarize_holdout_trends.py tests/test_audit_runtime_smoke_gate_replay.py` 为 `38 passed`，`tests/test_audit_runtime_smoke_replay.py` 为 `6 passed`，ruff 通过；本轮未调用外部 LLM、Docker 或 official eval。
- 2026-05-17 针对 `clog-tool__clog-cli.7066cba` / `jarun__nnn.cb2c535` 做了本地 runtime-smoke replay 交叉审计：latest official candidates 都缺 `input_files` 合约，仍卡在 `insufficient_contract_artifacts` / `runtime_smoke_not_passed`；`clog-cli` 较早候选虽然覆盖 `args,input_files,stdin`，但本地 `--execute` replay 结果为 `replay_failed`，`failed_issue_kind=runtime_smoke_error`。全量 `audit_runtime_smoke_gate_replay.py --execute-replay --min-smoke-contract-axes 1 --require-runtime-smoke-dimensions args,input_files --allow-existing-official` 没有发现 `metadata_only_runtime_smoke_blocker`；除 `chmln__sd.87d1ba5` 外，当前严格候选不是“只差 metadata”，不要重复把 `clog-cli` / `nnn` 当作可直接补证据的官方突破提交。
- 2026-05-17 `audit_runtime_smoke_gate_replay.py` JSON/markdown 新增 aggregate-only 字段 `replay_failed_issue_kind`，用于在 gate replay 输出中直接区分 `runtime_smoke_traceback`、`runtime_smoke_timeout`、`runtime_smoke_error` 等失败类别，不输出 argv、stderr、输入文件内容或 hidden failure。focused `tests/test_audit_runtime_smoke_gate_replay.py` 为 `7 passed`，ruff 通过；该字段后续继续细分出 syntax/executor-permission 类别。
- 2026-05-17 `audit_runtime_smoke_gate_replay.py` 继续新增可重复 `--status` 与 `--replay-failed-issue-kind` 过滤，用于直接筛出 `metadata_already_sufficient`、`metadata_only_runtime_smoke_blocker` 或 runtime-smoke 失败类别。focused `tests/test_audit_runtime_smoke_gate_replay.py` 为 `10 passed`，ruff 通过；真实 `runs` 下 `--status metadata_only_runtime_smoke_blocker` 为 0 行，`--status metadata_already_sufficient` 仍只有 `chmln__sd.87d1ba5`。并行只读子代理复核严格 latest gate replay 也未发现除 `chmln__sd.87d1ba5` 外的新官方突破证据；其列出的 latest implementation replay 失败候选在当前 Codex sandbox 下主要先表现为 executor permission denied。
- 2026-05-17 Python runtime smoke 进一步把候选语法错误和执行环境权限问题拆开：运行前先对生成的 Python 文件做 AST syntax precheck，语法坏候选直接返回 `runtime_smoke_syntax_error`，不再启动子进程；若本地 executor 因 `[WinError 5]`/permission denied 无法启动嵌套 Python，则返回 `runtime_smoke_executor_permission_denied`，不再混入 generic `runtime_smoke_error`。focused regression：`tests/test_codebase_integrity.py tests/test_audit_runtime_smoke_replay.py tests/test_audit_runtime_smoke_gate_replay.py` 为 `32 passed`，ruff 通过。真实 `runs` 下 `tarka__xcp.5e5b448` gate replay 现在筛为 `runtime_smoke_syntax_error`；`hexyl` 部分历史 replay 在当前沙箱下为 executor permission blocker，不能当作候选实现失败或官方突破证据。
- 2026-05-17 `audit_runtime_smoke_gate_replay.py` 新增高层状态 `replay_environment_blocked`：当 replay 失败类别为 `runtime_smoke_executor_permission_denied` 时，不再归入 `replay_failed_or_incomplete`。focused `tests/test_audit_runtime_smoke_gate_replay.py` 为 `11 passed`，ruff 通过；真实 `runs` 下 `sharkdp__hexyl.2e26437 --latest-per-task` 可用 `--status replay_environment_blocked` 精确筛出，仍保留 `low_holdout_rate` / `runtime_smoke_not_passed` blocker，不把当前 Codex sandbox 限制误写成候选实现失败。
- 2026-05-17 strict latest gate replay JSON 已补 `status_counts` 与 `replay_failed_issue_kind_counts` 汇总。真实 `runs` 在 `--latest-per-task --min-smoke-contract-axes 1 --require-runtime-smoke-dimensions args,input_files --require-holdout-improvement --min-holdout-improvement-delta 0.02 --allow-existing-official --execute-replay --format json --limit 1` 下总计 23 行：`metadata_already_sufficient=1`、`replay_environment_blocked=4`、`replay_failed_or_incomplete=18`；失败类别统计为 `runtime_smoke_executor_permission_denied=4`、`runtime_smoke_syntax_error=2`。这仍是本地 aggregate/gate 证据，不是新的官方突破；除 `chmln__sd.87d1ba5` 外没有新的 strict official 候选。
- 2026-05-17 direct `audit_runtime_smoke_replay.py` 也补齐 `--status`、`--failed-issue-kind` / `--replay-failed-issue-kind` 过滤以及 JSON `status_counts` / `failed_issue_kind_counts`。focused `tests/test_audit_runtime_smoke_replay.py` 为 `8 passed`，ruff 通过；真实 `runs` 在 `--require-runtime-smoke-dimensions args,input_files --execute --format json --limit 1` 下总计 119 行：`insufficient_contract_artifacts=96`、`missing_entrypoint=4`、`replay_environment_blocked=16`、`replay_failed=3`；失败类别为 `runtime_smoke_executor_permission_denied=16`、`runtime_smoke_syntax_error=3`。这说明 direct replay 的主要缺口仍是 contract artifacts / input_files 覆盖，其次是当前 Codex sandbox 执行环境限制；不要把这些计数误读成官方隐藏测试突破。
- 2026-05-17 `audit_restore_targets.py` 新增可重复 `--task` 过滤，并在 JSON 输出 `regression_signal_counts` / `axis_delta_action_counts`。focused `tests/test_audit_restore_targets.py` 为 `6 passed`，ruff 通过；真实 `xsv` 单任务审计显示 latest holdout `0/16`、best `9/11`、`regression_delta=-81.8%`，`axis_delta_action=ablate_added_axis_domains:csv_table`；真实 `htmlq` 单任务审计显示 latest `7/16`、best `10/11`、`regression_delta=-47.2%`，`axis_delta_action=ablate_added_axis_domains:html_selector`。对应 `run_restore_axis_ablation_batch.py` JSON dry-run 已能分别打印只读 command plan，命令保留 `--skip-official-eval`、`--require-holdout-improvement`、`--max-generalization-risk low`、`--require-runtime-smoke-dimensions args,input_files` 和 `--dry-run`，未调用外部 LLM、Docker 或 official eval。
- 2026-05-17 针对真实 `burntsushi__xsv.f430466` replay syntax failure 继续定位，生成的 `main.py` 在 `f = open_input(ns.input` 处被截断，AST 报 `(` 未闭合。`CodebaseIntegrityChecker` 与 `PythonRuntimeSmokeChecker` 现在共享 `python_syntax_error_message()`，当语法错误形态像输出截断时，会在 issue message 中加入 `likely truncated generated output` 与 `compact complete source files` 提示；`ImplementerAgent` 的 retry prompt 会原样携带该提示，并且只在疑似截断时把 previous output preview 从单纯头部改成 head+tail，以便模型看到文件尾部截断点。issue kind 仍保持 `syntax_error` / `runtime_smoke_syntax_error`，不打乱既有 gate 统计。focused verification：`tests/test_codebase_integrity.py` 为 `18 passed`，retry prompt + integrity/replay/restore slice 为 `44 passed`，`python -m ruff check core\codebase\integrity.py core\codebase\runtime_smoke.py core\implementation\prompts.py tests\test_codebase_integrity.py tests\test_agent_output_parsing.py` 通过；真实 strict official-eligible JSON gate 仍为 `row_count=0`、`total_row_count=0`。未调用外部 LLM、Docker 或 official eval。
- 2026-05-17 `plan_official_breakthrough_targets.py` 的 restore-ablation command plan 已补 `--restore-ablation-require-runtime-smoke-dimensions`，用于把 strict runtime-smoke dimension gate 传给 `run_official_strategy_ablation.py` child command。focused TDD 先确认旧 CLI 不识别该 flag，再实现后 `tests/test_plan_official_breakthrough_targets.py` 为 `8 passed`，`python -m ruff check scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py` 通过。真实 `runs` JSON smoke 加 `--include-restore-ablation-command --restore-ablation-require-runtime-smoke-dimensions args,input_files` 后，`htmlq`、`xsv` 等 restore target 的 dry-run command 均包含 `--require-runtime-smoke-dimensions 'args,input_files'`；仍未执行外部 LLM、Docker 或 official eval。
- 2026-05-17 `summarize_holdout_trends.py` 的 weak-task recommendation command 也已补 `--rerun-require-runtime-smoke-dimensions`，用于把 strict runtime-smoke dimension gate 传给 `run_weak_task_cleanroom_rerun.py` guarded dry-run。focused TDD 先确认旧 `build_guarded_rerun_command()` 不接受 `required_runtime_smoke_dimensions`，实现后 `tests/test_summarize_holdout_trends.py` 为 `34 passed`，`python -m ruff check scripts\summarize_holdout_trends.py tests\test_summarize_holdout_trends.py` 通过。真实 `runs` JSON smoke 加 `--recommend-weak-reruns --include-rerun-command --rerun-min-smoke-contract-axes 1 --rerun-require-runtime-smoke-dimensions args,input_files --rerun-min-holdout-improvement-delta 0.02` 后，`hexyl`、`zoxide`、`pingu` 的 guarded command 均包含 `--require-runtime-smoke-dimensions args,input_files`；仍未执行外部 LLM、Docker 或 official eval。
- 2026-05-17 `plan_official_breakthrough_targets.py` 的剩余 weak/missing-holdout command plan 也已补 runtime-smoke 维度 gate：新增 `--rerun-require-runtime-smoke-dimensions` 和 `--missing-holdout-require-runtime-smoke-dimensions`，分别透传给 `run_weak_task_cleanroom_rerun.py` 与 `run_missing_holdout_cleanroom_rerun.py` child command。focused TDD 先确认旧 CLI 不识别两个 flag，再实现后 `tests/test_plan_official_breakthrough_targets.py` 为 `8 passed`，`python -m ruff check scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py` 通过。真实 `runs` planner JSON smoke 同时开启 ready/restore/weak/missing 四类 runtime-smoke dimension flags 后返回 `row_count=12`、`total_row_count=13`，四类 `next_command` 均包含 `--require-runtime-smoke-dimensions args,input_files`（planner shell quoting 下可能显示为 `'args,input_files'`）；去掉 `--allow-existing-official` 的 strict official-eligible gate 仍为 `row_count=0`、`total_row_count=0`，未调用外部 LLM、Docker 或 official eval。
- 2026-05-17 新增 `file_bridge` LLM provider，用于“官方测试集验证阶段不调用外部 LLM API”的本地接力：`llm_clients/file_bridge_client.py` 会把每次 chat 请求写成 `output/file_bridge_llm/request_<id>.json`，并等待同目录下 `response_<id>.json` 或 `response_<id>.txt`。`main.py --provider file_bridge` 已可选，`config/smoke_file_bridge.yaml` 也可直接传给 wrapper 的 `--config`。验证：`tests/test_file_bridge_client.py tests/test_config_env.py tests/test_main_controller_config.py` 为 `41 passed`，`python -m ruff check llm_clients\file_bridge_client.py llm_clients\factory.py main.py tests\test_file_bridge_client.py tests\test_config_env.py tests\test_main_controller_config.py` 通过。该 provider 本身不生成答案、不联网、不跑 Docker，也尚未执行 official eval；它只是让人工/Codex 子代理能在本地文件层填充 ReBuilder 的 LLM 响应。
- 2026-05-17 `DiffReport.is_equivalent` 已补 executor-error 防线：当原始与替代程序都因为本地执行器基础设施错误失败（如 Codex Windows sandbox 下的 `[WinError 5]`）时，不再把“同样失败”计为 behavioral equivalence。新增 TDD 覆盖后 `tests/test_differential_tester_backends.py` 为 `9 passed`，ruff 通过。随后用 escalated 本地 `file_bridge` harness 跑通 `examples/mock_task`：无外部 LLM，4 个 file response，生成 1 个 `main.py`，exploration `8/8`、holdout `2/2`、status `success`；产物在 `output\file_bridge_smoke_20260517_harness5\mock_task\result.json`。这验证的是本地桥接闭环，不是官方测试集突破；官方 eval 仍未执行。
- 2026-05-20 按“官方测试集标准在 ReBuilder 架构内用 LLM 推理”的边界继续硬化 `file_bridge`/子代理路径：真实 subagent adversarial 输出暴露 `input_files` 里 JSON-safe bytes（`{"__type__":"bytes","base64":"..."}`）无法回读为 `TestCase.input_files: dict[str, bytes]`，导致整批 adversarial 生成被 Pydantic 校验失败跳过。`core/llm_output.py` 现在会把 bytes payload 解码、普通字符串编码为 UTF-8 bytes，并过滤 `{"__type__":"directory"}` 等不可物化条目；unsafe 路径仍交给 executor 安全层过滤。验证：新增回归先失败后通过，focused `2 passed`，完整 `tests/test_differential_tester_backends.py` 为 `11 passed`，`python -m ruff check core\llm_output.py tests\test_differential_tester_backends.py` 和 `python -m py_compile core\llm_output.py tests\test_differential_tester_backends.py` 通过。困难边界已记录到 `docs/public-release-materials.md`：外部 Kimi/GLM fallback 因会发送本地 task/code context 被策略拒绝，上一轮 official eval Docker hang 未产出 aggregate eval JSON，Windows pytest temp ACL 仍会干扰宽测试，`mypy` 当前被既有 `core\data_models.py __test__` attr-defined 问题阻断。本轮修复提升本地 cleanroom 验证强度，但不是新的官方 ProgramBench 突破。
- 2026-05-20 继续补官方闭环韧性：`scripts/run_official_closed_loop.py` 新增显式 `--official-eval-timeout-seconds`，默认 0 保持旧行为，只有传参时才给 ProgramBench eval 的 subprocess 加 timeout；超时会转成清晰 `RuntimeError("Command timed out...")`，若没有 aggregate eval JSON 仍不得记录官方分数。`tests/test_run_official_closed_loop.py` 补了 timeout 传参、timeout 报错、wrapper 透传以及非法 timeout 参数拒绝。验证：focused timeout slice 为 `11 passed`，`python -m ruff check scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py` 通过，`python -m py_compile scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py` 通过。宽 `tests/test_run_official_closed_loop.py` 仍被当前 Windows sandbox 的 `tmp_path` ACL 拒绝阻断；这不是新增逻辑失败，已同步写入 `docs/public-release-materials.md`。只读子代理目标审查推荐下一轮 no-external `file_bridge` 官方标准闭环用 `chmln__sd.87d1ba5` + `config/smoke_file_bridge_subagent_chmln.yaml`，但其官方 aggregate 仍是 score 86、非 fully resolved，因此只能作为强 baseline/复核目标，不是新突破。
- 2026-05-20 按上述目标实际跑通一次 no-external-LLM `file_bridge` 官方标准闭环：responder 子代理处理 11 个本地 request（均写入 `output\file_bridge_llm_subagent_chmln_20260518\response_*.txt`，无 pending/未处理项），ReBuilder 本地结果为 exploration `43/49`（87.8%）、holdout `12/14`（85.7%）、status `FAILED`，但因 package gate 配置为 holdout >=0.8 且 runtime-smoke 维度满足，仍打包进入 ProgramBench official eval。官方 aggregate 结果：counted `651/810`，score `80`；raw `701/869`，score `81`；`fully_resolved=false`、`almost_resolved=false`。这证明子代理确实被放入 ReBuilder 架构内推理测试，但本轮比既有 chmln score-86 baseline 退步，不能算突破。过程中先遇到缺失 cleanroom image；`--pull` 又被 adapter 的 60s docker pull timeout 截断，后用直接 `docker pull programbench/chmln_1776_sd.87d1ba5:task_cleanroom` 成功拉取后继续。另发现 closed-loop 自动 baseline 记录会用更低 score 覆盖高分 baseline，已恢复 `baselines/programbench/chmln__sd.87d1ba5.baseline.json` 到 score 86，并在 `core/experiments/baseline.py` 增加 official aggregate rank 防回退逻辑；focused baseline tests `2 passed`，ruff/py_compile 通过。
- 2026-05-20 针对上述 cleanroom image 拉取困难补了准备阶段可配置超时：`scripts/prepare_programbench_task.py` 新增 `--docker-command-timeout-seconds`（默认仍 60s），`scripts/run_official_closed_loop.py` 会透传该参数到 prepare 子进程；`SubprocessDockerClient` 现在把 Docker CLI 超时转成清晰 `RuntimeError("Command timed out...")`。这不会改变 cleanroom 边界，也不会放宽 official eval 证据标准，只是避免慢网络首拉镜像时反复卡在硬编码 60s。验证：Docker timeout focused slice 为 `18 passed`，`python -m ruff check core\programbench\adapter.py scripts\prepare_programbench_task.py scripts\run_official_closed_loop.py tests\test_programbench_adapter.py tests\test_programbench_catalog.py tests\test_run_official_closed_loop.py` 通过。
- 2026-05-20 继续修正 official-baseline upgrade 防误报：`scripts/run_official_closed_loop.py` 会把官方 eval 的 aggregate-only raw/counted 摘要写回 candidate `result.json` 的 `official_eval_summary`；`scripts/rank_programbench_candidates.py` 对已有 official/baseline 的任务不再只凭 local holdout/runtime-smoke gate 标成 `eligible_baseline_upgrade`，必须存在嵌入的官方聚合摘要且官方 rank 高于已记录 baseline，否则 blocker 为 `missing_official_candidate_summary` 或 `official_not_above_baseline`。真实 strict ranking gate 现在在 `--allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files` 下返回 `row_count=0`；planner 仍列出 `chroma/gron/nnn/chmln/htmlq/cmatrix` 等 audit target，但 ready-baseline gate 均不会被误认为已可升级。验证：ruff/py_compile 通过；手工 fixture 覆盖缺 summary、胜过 baseline、低于 baseline 和 summary 写回。`pytest --basetemp=runs\pytest_tmp_rank_gate` 仍被当前 Windows ACL 阻断，属于验证环境问题，已记录到 `docs/public-release-materials.md`。
- 2026-05-20 继续按 no-external-LLM `file_bridge` 子代理路径尝试 `alecthomas__chroma.8d04def` 官方标准闭环：本地候选进入 package/official eval 前达到 holdout `15/18`（83.3%），runtime smoke 覆盖 args/stdin/input_files/default；ProgramBench official eval 启动后在 Docker 侧反复长时间无 aggregate 输出，最终未产生 `*.eval.json`，因此没有官方分数、没有 baseline upgrade、也不是突破。已手动停止残留 ProgramBench eval 容器，并在 `scripts/run_official_closed_loop.py` 增加失败且无 aggregate JSON 时的 `programbench-*` 容器清理，只匹配当前 instance 的 `programbench-compiled/<instance_id>:` 镜像。验证：新增 focused cleanup tests 先 RED 后 `2 passed`，`python -m ruff check scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py` 通过，`.\.venv\Scripts\python.exe -m py_compile scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py` 通过，`docker ps` 确认无运行中的 `programbench-*` 容器。宽 `tests\test_run_official_closed_loop.py` 仍被 Windows `tmp_path`/`basetemp` ACL 阻断，不属于本次逻辑回归。
- 2026-05-20 对同一 `alecthomas__chroma.8d04def` 继续做 `restore_patch2` no-external `file_bridge` 复核：在不使用 Kimi/GLM 的前提下，先修正 CLI 边界（missing value 诊断、long/short unknown flag 优先级、文件校验早于 help/list/html-styles、动态 `/rebuilder-work/<path>` 缺失/目录诊断），再用上一轮公开 evidence store 离线复放 `122/122` 无 mismatch。新的 ReBuilder local closed-loop 为 exploration `95/95`、holdout `31/31`，runtime smoke 覆盖 args/stdin/input_files/default，并已打包到 `runs\programbench_official_eval\submission_chroma_restore_patch2_20260520`。第一次官方 eval 等待 30 分钟仍未产出 `*.eval.json`，并留下一个 chroma ProgramBench 容器需要手动停止；随后发现第一次的 Python eval 进程仍存活并与新后台 eval 指向同一 submission 目录，已停止该孤儿进程和旧容器，避免并发写入污染 aggregate 输出。第二次后台 eval 仍无 aggregate JSON 且容器表现为长时间挂起，已停止后台进程和容器。当前状态仍不得声明突破或 baseline upgrade；只能记录为强本地候选遇到官方 eval 操作性阻塞。
- 2026-05-20 复用同一 `chroma restore_patch2` `submission.tar.gz` 做 bounded 官方 eval 重试，不重新调用 file_bridge/LLM，也不使用 Kimi/GLM。参数为 `workers=1`、`branch_workers=1`、`docker_cpus=4`、`branch_retries=1`、`force=True`、`official_eval_timeout_seconds=600`。结果仍停在 `Fetching ... files: 3it` 后超时，无 `alecthomas__chroma.8d04def.eval.json`；runner cleanup 停掉 1 个 matching ProgramBench eval container。随后 elevated `docker ps` 与进程查询确认没有残留 `programbench`/`chroma` 容器或旧 Python eval 进程。结论不变：chroma 是强本地候选，但没有官方 aggregate JSON，不能声明官方突破。
- 2026-05-20 为上述官方 eval hang 增加 durable 运维记录：`run_official_closed_loop.py` 在 ProgramBench eval 失败且没有 `*.eval.json` 时会写 `official_eval_failure_report.json`，记录 command、timeout、workers/branch workers/docker cpus、stopped container ids，以及 submission/eval_json/root stdout/stderr log 的文件元数据；不读取或摘要官方测试详情。验证：`python -m ruff check scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py` 通过，`.venv` `py_compile` 通过；手工 harness `output\manual_smoke\official_eval_failure_report_20260520` 模拟超时并确认 report 字段。focused pytest 子集仍在 `output\pytest_tmp2\closed_loop_report_pytest_20260520` basetemp cleanup 报 `WinError 5`，目录已删除，不能写成 pytest passed。
- 2026-05-20 对同一 `chroma restore_patch2` package 做第二次 bounded 官方 eval 复核，仍不重新调用 file_bridge/LLM，也不使用 Kimi/GLM。参数为 `workers=1`、`branch_workers=1`、`docker_cpus=1`、`branch_retries=1`、`force=True`、`official_eval_timeout_seconds=1800`。结果仍停在 `Fetching ... files: 3it` 后超时，无 `alecthomas__chroma.8d04def.eval.json`。本轮 runner cleanup 停掉 1 个 matching eval container，并清理 7 个 `programbench-compiled/alecthomas__chroma.8d04def:*` compiled images；`official_eval_failure_report.json` 已记录 `removed_compiled_image_count=7` 和具体 refs。后续 elevated Docker 检查确认没有运行中的 `programbench-*` 容器，也没有残留 chroma compiled image。结论仍是 official eval 操作性阻塞，不能声明官方分数或突破。验证：`ruff` 和 `.venv` `py_compile` 通过；新增 image cleanup isolated pytest 为 `1 passed`；带 `tmp_path` 的 focused pytest 仍被 Windows basetemp ACL 阻断，不能写成 pytest passed。
- 2026-05-20 对 `chroma restore_patch2` 追加 long 官方 eval 复核：重新把同一 no-external `file_bridge` generated code 打包到 `runs\programbench_official_eval\submission_chroma_restore_patch2_long_20260520`，不重新调用 LLM/file_bridge，也不使用 Kimi/GLM。ProgramBench eval 参数为 `workers=1`、`branch_workers=1`、`docker_cpus=2`、`branch_retries=1`、`force=True`；shell wrapper 在 7200 秒超时退出，但目录中已写出官方 aggregate JSON。结果为 counted `0/515`、score `0`，raw `0/531`、score `0`，低于历史 chroma score-3 baseline，因此不是突破、不能更新 baseline。已把 aggregate-only `official_eval_summary` 回填到该候选 `result.json`，后续 planner/ranking 应将其归为不高于 baseline，而不是继续当作未评测 ready candidate。困难记录：本地 exploration/holdout 均为 100% 仍可能在官方 aggregate 归零，说明 local gate 对 chroma 的预测力不足；同时官方 eval 仍有极长耗时/timeout 操作成本。
- 2026-05-20 追加修复同一类 official-baseline upgrade 防误报的单候选路径：真实 `chroma` score-0 summary 回填后，`rank_programbench_candidates.py` strict gate 已返回 `row_count=0`，但 `scripts/audit_official_eval_gate.py` 因没有把 baseline official ranks 传给 `read_candidate_row()`，仍把该候选报告成 `eligible_baseline_upgrade`。现已改为读取 `discover_baseline_official_ranks()` 并传入 candidate row；真实 `chroma` audit 现在返回 `eligible=false`、`reason=official_not_above_baseline`。新增回归覆盖“candidate official summary 低于 baseline 必须阻断”。验证：elevated focused pytest `tests\test_audit_official_eval_gate.py tests\test_rank_programbench_candidates.py` 为 `98 passed`；非 elevated pytest 仍被 Windows `tmp_path`/`basetemp` ACL 阻断（默认 `.codex-tmp`、`C:\tmp`、仓库内 basetemp 均出现 `WinError 5`），这是验证环境限制，不是逻辑失败。
- 2026-05-20 追加复核 `tomnomnom__gron.88a6234` no-external `file_bridge` patch6：只读子代理先确认该候选来自本地 bridge request/response 路径，未使用外部 LLM；随后官方 ProgramBench aggregate eval 成功完成，但 counted `140/224`、score `62`，raw `148/233`、score `64`，与已记录 gron score-62 baseline 持平，因此不是突破。这个结果暴露 planner 另一处同分误报：`plan_official_breakthrough_targets.py` 的 `baseline_upgrade_gate` 以前没有把 baseline official ranks 传给 `read_candidate_row()`，导致嵌入官方 summary 但不高于 baseline 的候选仍可能被标成 eligible。现已修复为等分/低分统一返回 `official_not_above_baseline`，并补测试 `test_json_ready_rows_block_equal_official_summary_as_not_above_baseline`。同时把已有官方 eval JSON 的 aggregate-only summary 回填到 `gron/nnn/htmlq/chmln/cmatrix` 候选 `result.json`；strict official-ready gate 仍为 `row_count=0`，其中 `gron/nnn/htmlq/chmln/cmatrix` 均被 `official_not_above_baseline` 阻断，`nnn` 还保留 `runtime_smoke_not_passed`；`chroma restore_patch2` 现已回填 score-0 official summary，低于历史 score-3 baseline，因此同样不能声明官方突破。
- 2026-05-20 下一轮目标选择：重新跑 strict ranking gate 仍为 `row_count=0`；`nnn` 的 runtime-smoke gate replay 即使 `--execute-replay` 也返回 `insufficient_contract_artifacts`，缺 `input_files`，所以不是可直接补证据的官方候选。当前更合理的 no-external 准备目标是 `clog-tool__clog-cli.7066cba` 的 restore-axis ablation：它属于 `ablate_added_axis_domains:filesystem_tool,go_dependency_report`，且已有 `output\file_bridge_manual\smoke_file_bridge_clog_from_latest_patch4.yaml` 可作为 file_bridge 配置。已生成不执行的 dry-run 命令计划，保留 `--skip-official-eval`、`--require-holdout-improvement`、`--max-generalization-risk low`、`--require-runtime-smoke-dimensions args,input_files`；只有该本地 ablation 重新过 gate 后，才应进入官方 ProgramBench eval。
- 2026-05-20 继续按“官方测试集标准在 ReBuilder 架构内用 LLM 推理”的要求执行 `clog-tool__clog-cli.7066cba` restore-axis ablation，使用本地 `file_bridge` 响应路径，没有调用外部 Kimi/GLM。`adaptive_profile` 首轮 `--max-repairs=2` 为 exploration `33/60`、holdout `14/18`（77.8%），未过 `0.8` gate；near-miss 自动重试 `--max-repairs=5` 后最佳 accepted candidate 为 exploration `41/60`（68.3%），但最终 holdout 仍为 `14/18`（77.8%），因此按配置跳过 official eval。结果文件：`runs\restore_axis_ablation_clog_resume\adaptive_profile\clog-tool__clog-cli.7066cba\generated\clog-tool__clog-cli.7066cba\clog-tool__clog-cli.7066cba\result.json`；failure aggregate：`runs\restore_axis_ablation_clog_resume\adaptive_profile\clog-tool__clog-cli.7066cba\reports\clog-tool__clog-cli.7066cba.exploration.failures.json`。困难点主要是 `changelog written. (took N ms)` 精确 stdout 时间、Unicode/空格 outfile 的 file-output 对齐、`--changelog` conflict usage、以及 `--version` 与无效参数的优先级；多个 repair 被 non-regression gate 拒绝。strict official-eligible JSON gate 复核仍为 `row_count=0`。本轮子代理 responder 不稳定，主会话补齐了后续 file_bridge 响应；这要记录为 responder 编排困难，不要误写成已经使用或必须使用 Kimi。
- 2026-05-20 继续推进同一 `clog-tool__clog-cli.7066cba` no-external `file_bridge` 路径：主会话先把本地差分比较中的两类 Windows-vs-Docker 噪声收敛到 `core\differential_tester.py`，只窄归一化 `changelog written. (took N ms)` 这类耗时计数，并只容忍 UTF-8 文本 file output 的 CRLF/LF 差异，二进制输出和非耗时正文仍严格比较。随后手工 `patch5` 修复空版本头、缺 `.git` 默认上下文 fallback、LF 写文件等 cleanroom-local 行为。ReBuilder local 结果提升到 exploration `105/106`、holdout `15/16`、status `success`，runtime smoke 覆盖 args/default/input_files/stdin，`--max-local-holdout-gap 0.15` strict package gate 通过；ProgramBench official eval 完成，counted `260/575`、score `45`，raw `394/778`、score `51`，`fully_resolved=false`。这比旧 clog score-45 baseline 的 `257/575` counted 多 3 个，但 rounded official score 未提升，所以只记录为同分 aggregate refinement，不是官方 score breakthrough。baseline 已更新到 `baselines\programbench\clog-tool__clog-cli.7066cba.baseline.json`，submission SHA-256 为 `ab2011ab685708df8fa9b280a880bc9b191ac472f782faa2ed5661ed2df62bac`。验证：`ruff`、`.venv` `py_compile` 和 `tests\test_differential_tester_backends.py` focused pytest `17 passed`；pytest 仍有既有 `.pytest_cache` ACL warning。剩余困难是一条 visible local git-repo outfile file-output mismatch，不能写成 official hidden failure。
- 2026-05-20 继续复核 `psampaz__go-mod-outdated.bb79367` no-external `file_bridge` 子代理候选。子代理先在 `output\file_bridge_manual\run_go_mod_file_bridge.py` 准备 `table_patch4`，主会话随后把 Go log stderr 的秒级时间漂移收敛为 `core\differential_tester.py` 的窄归一化：仅当行数一致、非时间戳正文一致、时间戳可解析且相差不超过 2 秒时才认为等价。最终 ReBuilder local closed-loop 为 exploration `23/23`、holdout `7/7`、runtime smoke passed，维度覆盖 args/stdin/input_files/default；官方 ProgramBench eval 完成，counted `229/285`、score `80`，raw `277/342`、score `81`，`fully_resolved=false`。这把 go-mod 记录 baseline 从 score 15 升到 score 80，是 aggregate baseline upgrade，但不是 solved-task。产物：`runs\programbench_official_eval\submission_go_mod_outdated_table_patch4_20260520\psampaz__go-mod-outdated.bb79367\psampaz__go-mod-outdated.bb79367.eval.json`；baseline：`baselines\programbench\psampaz__go-mod-outdated.bb79367.baseline.json`。困难记录：本任务只有 7 个 internal holdout cases，因此官方 eval 使用显式 `--min-holdout-cases 7`，不要包装成默认 10-case gate；Docker/ProgramBench 需要本地镜像与 elevated Docker access；pytest 仍有 `.pytest_cache` ACL warning。验证：`tests\test_differential_tester_backends.py` 为 `13 passed`，official eval 后 strict ranking gate 仍为 `row_count=0`。
- 2026-05-20 继续按“官方测试集标准在 ReBuilder 架构内用 LLM 推理”的要求复核同一 `psampaz__go-mod-outdated.bb79367`。`Cicero` 子代理做只读目标审计，确认 go-mod 是当前最合适的 restore_historical_gate 候选；`Hypatia` 子代理只基于公开 Go CLI/JSON/module 语义提出 table_patch5 机制补强，不读取官方隐藏失败细节。主会话在 `output\file_bridge_manual\run_go_mod_file_bridge.py` 增加 `table_patch5`：处理 Go-style `--` 终止符、bool flag forms、`json.Decoder` 截断错误、module `Replace`/`Update` 零值、filtered `-ci`、Unicode display-width 表格对齐，并移除新生成 config 里的外部 provider 段。focused TDD 先红后绿，`tests\test_go_mod_file_bridge_harness.py` 为 `4 passed`，`py_compile` 与 `python -m ruff check` 通过。第一次 strict gate 因 holdout cases 只有 7 个被正确阻断；把 table_patch5 holdout ratio 提到 0.4 后，ReBuilder no-external local gate 为 exploration `19/19`、holdout `11/11`、runtime smoke 覆盖 args/default/input_files/stdin。官方 ProgramBench aggregate eval 完成：counted `267/285`、score `94`，raw `316/342`、score `92`，`fully_resolved=false`、`almost_resolved=false`。这把 go-mod 记录 baseline 从 table_patch4 的 score 80 升到 score 94，是新的 official aggregate baseline upgrade，但仍不是 solved task；baseline 更新后 strict official-ready ranker 在 required dimensions `args,input_files,stdin` 和 `--max-local-holdout-gap 0.15` 下返回 `row_count=0`。产物：`runs\programbench_official_eval\submission_go_mod_outdated_table_patch5_20260520\psampaz__go-mod-outdated.bb79367\psampaz__go-mod-outdated.bb79367.eval.json`；baseline：`baselines\programbench\psampaz__go-mod-outdated.bb79367.baseline.json`；submission SHA-256：`abc79e8e3140009a4a214bb5e13ff3fb00f7eb2d1aee0309e1b9dd733f6d8913`。困难记录：cleanroom image 初始缺失，需要 `--pull`；Windows sandbox pytest 临时目录反复 `WinError 5`，需显式 `C:\tmp` basetemp/elevated 运行；仓库 `.venv` 缺 `ruff`，lint 使用 project-level `python -m ruff`；不得把官方 hidden failure 细节写入修复叙事或后续 prompt。
- 2026-05-20 在用户要求继续“把子代理放入 ReBuilder 架构并按官方测试集标准推理”的上下文下，追加两路只读子代理审计：一组复核 strict ranker/planner，另一组盘点 `output\file_bridge_manual` harness。结论是当前不应直接 official eval，也不应立刻切到 Kimi K2.6 fallback：`file_bridge` 子代理路径已经能在 ReBuilder 内推理并完成官方 aggregate eval，真正 blocker 是 strict gate 没有任何高于 baseline 的候选。最新 strict official-ready ranker 在 `--allow-existing-official --official-eligible-only --latest-per-task --require-runtime-smoke-dimensions args,input_files,stdin --max-local-holdout-gap 0.15` 下仍为 `row_count=0`；aggregate-only generalization-gap 审计返回 10 行，其中 `chmln` candidate score 80 低于 score-86 baseline，`chroma restore_patch2` 本地 exploration/holdout 均 100% 但 official aggregate score 0 低于历史 score-3 baseline，`htmlq` score 91 但 counted 比 baseline 少 1，`go-mod` score 94 已等于当前记录 baseline。因此下一步必须先做新的本地机制/泛化修复或更强 unseen evidence，而不是重复提交官方评测或把“没有可提交候选”误记成需要外部 LLM。
- 2026-05-20 继续尝试 `agourlay__zip-password-finder.704700d` no-external `file_bridge` restore 候选：两个 helper 子代理在等待窗口内未返回可用产物并已关闭，主会话随后在 `output\file_bridge_manual\run_zip_file_bridge.py` 补了本地 bridge harness。该 harness 从历史 best cleanroom artifact 出发，只做 CLI usage 诊断修补，不调用外部 Kimi/GLM。ReBuilder local gate 为 exploration `92/98`（93.9%）、holdout `13/16`（81.2%），runtime smoke passed，维度覆盖 args/stdin/input_files/default，并成功打包进入官方 eval。ProgramBench official aggregate 结果为 counted `248/680`、score `36`，raw `340/792`、score `43`，与既有 zip score-36 baseline 持平，`fully_resolved=false`，因此不是突破。产物：`runs\programbench_official_eval\submission_zip_password_finder_usage_patch1_20260520\agourlay__zip-password-finder.704700d\agourlay__zip-password-finder.704700d.eval.json`。困难记录：zip cleanroom image 初始缺失，需要 `docker pull programbench/agourlay_1776_zip-password-finder.704700d:task_cleanroom`；sandbox 内仍检测不到已拉取镜像，closed loop 需要 elevated Docker access；本地剩余失败主要是 parser/validation precedence 类，不要把它包装成 official hidden failure。
- 2026-05-20 继续推进同一 `agourlay__zip-password-finder.704700d` no-external `file_bridge` 路径，新增 `usage_patch2`：主会话在 `output\file_bridge_manual\run_zip_file_bridge.py` 修复公开本地暴露的 CLI parser/validation precedence，包括 unknown charset option 先于 ZIP 解析、缺值诊断带 `<flag>` placeholder、显式 u64 参数类型校验先于 required inputFile，以及 harness 透传 `--pull`。focused TDD 先红后绿，`tests\test_zip_file_bridge_harness.py` 为 `3 passed`。ReBuilder local gate 为 exploration `98/98`、holdout `13/16`（81.2%）、runtime smoke 覆盖 args/default/input_files/stdin，并成功进入官方 eval。ProgramBench official aggregate 完成：counted `274/680`、score `40`，raw `366/792`、score `46`，`fully_resolved=false`、`almost_resolved=false`。这把 zip 记录 baseline 从 score 36 升到 score 40，是 official aggregate baseline upgrade，但不是 solved task；baseline 更新到 `baselines\programbench\agourlay__zip-password-finder.704700d.baseline.json`，submission SHA-256 为 `2dfa91d5a573f4da025988621e9bbbca78c564726940c87fe9291e6c11a9a8fe`。困难记录：cleanroom image 初始缺失，需要 `--pull` 和 elevated Docker；Windows sandbox pytest 临时目录继续出现 `WinError 5`，需 elevated focused pytest 并清理本轮 tmp；不要使用或发布官方 hidden case 级失败细节。
- 2026-05-20 继续执行 `burntsushi__xsv.f430466` no-external `file_bridge` restore_patch1：先从历史 best `closed_loop_official_20260513_xsv_strategy_pack_v2` 恢复可编译实现，对本地 aggregate failures 做三轮窄修复。第一轮 local gate 为 exploration `76/103`、holdout `9/15`（60.0%），第二轮为 exploration `78/102`、holdout `11/15`（73.3%），第三轮达到 exploration `82/102`（本地 official rerun 中为 `81/102`）、holdout `12/15`（80.0%），runtime smoke passed，维度覆盖 args/stdin/input_files/default，才进入官方 eval。ProgramBench official aggregate 完成：counted `527/1186`、score `44`，raw `604/1317`、score `46`，`fully_resolved=false`。这相对旧 xsv score-44 记录提高了 counted passed tests（旧记录 `518/1186`），但 rounded official score 未提高，所以只能记为同分 aggregate refinement，不是官方 score 突破。产物：`runs\programbench_official_eval\submission_xsv_restore_patch1_20260520\burntsushi__xsv.f430466\burntsushi__xsv.f430466.eval.json`；baseline 记录更新到同 score 下更高 counted passed。困难记录：xsv cleanroom image 初始缺失，需要 `docker pull programbench/burntsushi_1776_xsv.f430466:task_cleanroom`；sandbox 内仍检测不到已拉取镜像，closed loop 需要 elevated Docker access；本地修复主要集中在 CSV command dispatch、index/split sidecar file output、fixlengths stdin 诊断、top-level unknown flag 诊断、stats/frequency 精确输出。不要把这些本地 failure clusters 写成官方 hidden failure。
- 2026-05-20 继续尝试 `wfxr__csview.8ac4de0` no-external `file_bridge` same-axis restore：从 historical best artifact 恢复后做 `restore_patch1` 到 `restore_patch8` 本地桥接修复。`restore_patch4` 曾达到 exploration `43/49`、holdout `8/14`；随后按只读子代理建议补 `--padding/-p`、`--indent/-i`、`--sniff` 非法整数的 clap/Rust 风格 stderr，修复多 positional 下 `-` sentinel 泄漏，再补 `--style` 缺值 possible-values 和 unknown long flag tip。最终 `restore_patch8` 达到 exploration `49/49`，但 holdout 仍为 `8/14`，runtime smoke 仍只覆盖 args/default/stdin，缺 required `input_files` 维度，因此没有进入 ProgramBench official eval，也没有 score/baseline 更新。可对外说这是 same-axis restore 的强负证据：公开 exploration 精确修复没有泛化到 holdout；不可写成 official hidden failure 或 Kimi 结果。本轮仍未调用外部 Kimi/GLM。
- 后续 `csview` 不应直接包装 latest 或当前 `restore_patch8`。下一次必须先在本地恢复到不低于 historical best 的水平（历史 `resolved_rate=0.9231`、holdout `0.9167`），并补足 runtime-smoke `input_files` 维度，再考虑 official aggregate eval；否则只会重复把 local exploration 改进误当作官方候选。
- 2026-05-20 后续已按这个边界完成 `csview` axis-ablation contractfix：子代理通过 ReBuilder `file_bridge` 响应 4 个本地请求，无外部 Kimi/GLM；`core\spec_synthesizer.py` 修复大 corpus 截断时 sparse input-files contracts 丢失，`core\codebase\runtime_smoke.py` 修复 error contracts 挤占 input-files smoke budget。新本地结果为 exploration `35/35`、holdout `12/12`、runtime smoke 覆盖 args/default/input_files/stdin；复用 packaged submission 完成 ProgramBench official aggregate eval，counted `291/335`、score `87`，raw `303/348`、score `87`，相对旧 `csview` score-57 baseline 是官方 aggregate baseline upgrade，但不是 solved task。第一次 official eval 因 Windows GBK 输出解码/编码失败和 ProgramBench `NoneType + str` 失败，设置 `PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8` 后同一 package 成功完成。baseline 已更新到 `baselines\programbench\wfxr__csview.8ac4de0.baseline.json`，修复/困难记录已写入 `docs\public-release-materials.md`。
- 2026-05-20 追加反过拟合门禁：`rank_programbench_candidates.py` 新增 `--max-local-holdout-gap` 和 JSON/markdown `local_holdout_gap` 字段，`audit_generalization_risk.py` 新增 `latest_local_resolved_rate` / `latest_local_holdout_gap` 字段，并会把 otherwise gate-ready 但 local 明显高于 holdout 的候选标成 `local_holdout_gap_too_high`、要求先扩展 unseen holdout。真实 `runs` strict official-ready gate 加 `--max-local-holdout-gap 0.15` 仍为 `row_count=0`；`csview restore_patch8` 的 local `1.0`、holdout `0.5714`、gap `0.4286` 已在 aggregate 风险输出中显式暴露，但排名 gate 仍以 `low_holdout_rate` 和缺 `input_files` runtime-smoke 为主阻断，避免重复报同一类失败。本轮验证：`python -m ruff check scripts\rank_programbench_candidates.py scripts\audit_generalization_risk.py tests\test_rank_programbench_candidates.py tests\test_audit_generalization_risk.py` 通过，`.venv` `py_compile` 通过，手工 aggregate fixture harness 通过，真实 risk JSON `--fail-on-risk high` 返回 exit 2 且 JSON 可解析为 13 行/5 个 high。focused pytest 仍被 Windows temp/basetemp ACL 阻断，不能写成 pytest passed。
- 2026-05-20 继续把上述 gap 门禁接到 official-entry 命令链：`package_submission.py` 新增 `--max-local-holdout-gap` 并传给 `collect_generalization_risks()`；`run_official_closed_loop.py`、`run_official_strategy_ablation.py`、`run_restore_axis_ablation_batch.py` 会把同一阈值透传到 child package/closed-loop/strategy 命令。默认仍是 `0.15`，不会放宽现有 gate。验证：`python -m ruff check scripts\package_submission.py scripts\run_official_closed_loop.py scripts\run_official_strategy_ablation.py scripts\run_restore_axis_ablation_batch.py tests\test_submission_holdout_gate.py tests\test_run_official_closed_loop.py tests\test_run_official_strategy_ablation.py tests\test_run_restore_axis_ablation_batch.py` 通过，`.venv` `py_compile` 通过，手工 entrypoint harness 验证 package 会因 `local_holdout_gap_too_high` 拒绝候选，closed-loop / strategy / restore-batch command 均包含 `--max-local-holdout-gap 0.1`。真实 restore-axis JSON dry-run 选择 `clog-tool__clog-cli.7066cba`，child command 包含 `--max-local-holdout-gap 0.15`；strict official-ready gate 仍为 `row_count=0`。focused pytest 仍因当前 Windows temp ACL 未作为本轮通过证据。
- 2026-05-20 继续把 gap 门禁补到 planner 生成命令层：`plan_official_breakthrough_targets.py` 新增 `--baseline-upgrade-max-local-holdout-gap` 与 `--restore-ablation-max-local-holdout-gap`，ready-baseline gate JSON 记录 `max_local_holdout_gap` 并把阈值传给 `official_gate_blockers()` / `official_gate_reason()`，ready/restore `next_command` 均会带 `--max-local-holdout-gap`。验证：`python -m ruff check scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py` 通过，`.venv` `py_compile` 通过；真实 planner JSON smoke 返回 `row_count=13`、`ready_with_gap=8`、`restore_with_gap=3`；synthetic official-summary-above-baseline fixture 在 local `1.0`、holdout `0.85`、gap 阈值 `0.1` 下被 `local_holdout_gap_too_high` 阻断；strict official-ready gate 仍为 `row_count=0`。尝试 `pytest tests\test_plan_official_breakthrough_targets.py -q --basetemp output\pytest_tmp2\plan_gap_pytest_20260520` 时 pytest cleanup 对 basetemp 报 `WinError 5`，生成目录已确认在 workspace 内并删除，不能写成 pytest passed。
- 2026-05-20 继续按“子代理必须进入 ReBuilder 架构内推理”的要求复核 `rbakbashev__elfcat.52f8cc7`，使用 no-external `file_bridge` 配置 `output\file_bridge_manual\smoke_file_bridge_elfcat_holdout_probe1.yaml`，未调用外部 Kimi/GLM。第一次不带 `--pull` 因 cleanroom image 缺失在启动前失败；补 `--pull` 后首轮本地 56 probes、holdout `11/14`（78.6%），低于 gate，未进入官方 eval。near-miss retry 扩到 68 probes，最终 exploration `36/56`（64.3%）、holdout `14/16`（87.5%）、status `FAILED`、`almost_resolved=false`，先按 missing-holdout wrapper 打包到 `runs\programbench_official_eval\submission_rbakbashev_elfcat_52f8cc7\rbakbashev__elfcat.52f8cc7\submission.tar.gz`；随后复用该 package 做 bounded ProgramBench official eval，不重新调用 LLM/file_bridge。第一次手工 official eval 被默认 HuggingFace cache `C:\Users\Administrator\.cache` 权限拒绝，已删除误写的 `invalid_eval_payload` 摘要；第二次把 HF cache 切到 `output\hf_cache` 后又被 Docker API 权限阻断；最终 elevated Docker official eval 跑完，counted `215/564`、score `38`，raw `288/646`、score `45`，`fully_resolved=false`、`almost_resolved=false`。这把 elfcat 从历史 score-17 baseline 升到 score 38，baseline 已更新到 `baselines\programbench\rbakbashev__elfcat.52f8cc7.baseline.json`。修复/困难记录：`file_bridge` 实现响应必须是 manifest/file-block 结构，裸 Python 会被判 `missing_entrypoint`；JSON-safe bytes 的 `input_files` 可用；unsupported ELF class/data 的精确 stderr 有影响；主要未解 blocker 是本地 `file_output`/HTML bytes 对齐，多个 file-output repair 被 non-regression gate 拒绝，unsafe parent-traversal input file 被安全过滤跳过。可写成官方 aggregate baseline upgrade，但不能写成 solved task 或 fully resolved。
- 2026-05-20 继续修复 official-generalization gap 自动化边界：`scripts\audit_official_generalization_gaps.py` 现在输出 `official_eval_allowed=false`、`repeat_official_eval_recommended=false`、`evidence_boundary=aggregate_official_not_above_baseline`、`local_holdout_gap`、local/holdout-to-official pass-rate gap，并支持 `--include-next-command` 生成只重跑 aggregate-only 审计的 task-scoped 命令；新增 `--max-local-holdout-gap` 与现有反过拟合 ranker 对齐，新增 `--fail-on-gap` 在仍有 gap 时打印 JSON 后返回 exit 1，防止上游流程把 10 个 blocked gap 当成可继续 official eval 或切 Kimi K2.6 的信号。Beauvoir/Kant 子代理只读审计均建议补 raw aggregate/`total_tests`，现已补 counted `total_tests`、candidate raw aggregate、baseline raw aggregate（仅当 baseline submission sibling eval JSON 在本地存在）和 raw score/passed deltas；随后补 `--sort-by diagnostic-priority`、`generalization_failure_mode`、`diagnostic_priority`，用于优先排查本地/holdout 全绿但官方 aggregate 归零的泛化断裂；这些字段只来自 `official_eval_summary` 和 `ProgramBenchEvalParser` 聚合结果，测试确认不会输出 hidden marker。验证：elevated focused pytest `tests\test_audit_official_generalization_gaps.py` 为 `8 passed`；`.venv` `py_compile` 和 `python -m ruff check scripts\audit_official_generalization_gaps.py tests\test_audit_official_generalization_gaps.py` 通过；真实 gap smoke 返回 `total_row_count=10`、`official_regressed=3`、`official_equal_baseline=7`、`would_fail=true`，且 diagnostic 排序把 `chroma` 排第 1，模式为 `official_collapse_after_local_green`、priority `101.0`；真实 `chroma` task-scoped smoke 显示本地/holdout 均 `1.0`，但 counted official `0/515`、raw official `0/531`，低于 counted baseline `13/515`，因此它是本地泛化失真探针而不是可提交候选；strict official-ready ranker在 `--allow-existing-official --official-eligible-only --latest-per-task --require-runtime-smoke-dimensions args,input_files,stdin --max-local-holdout-gap 0.15` 下仍为 `row_count=0`。困难记录：普通 sandbox pytest 仍会把 basetemp 建成当前进程也无法枚举的目录并报 `WinError 5`，本轮清理了明确由本次 pytest 生成的临时目录；普通 `git status` 还会遇到 dubious ownership，需要临时 `git -c safe.directory=...` 只读状态，不写全局配置；旧 baseline 若没有本地 eval JSON 路径，raw baseline 保持 `null`，不要从 notes 文本反推。
- 2026-05-20 追加 official-eval failure-report gate 修复：`rank_programbench_candidates.py` 现在会从候选 run 的 sibling submission 目录或显式 `--official-eval-root` 下发现 `official_eval_failure_report.json`，把无 `eval.json` 的官方尝试标成 `has_official_eval=true`，并只暴露 `official_eval_failure_reason` / `official_eval_failure_report_path`。`plan_official_breakthrough_targets.py` 会把这类行归为 `target_class=official_eval_operational_failure`、`next_action=repair_official_eval_harness_before_more_official_eval`，避免 `chroma` generalization-probe 这种 3600 秒超时无 aggregate 的尝试继续显示成 `missing_official_candidate_summary`。验证：`py_compile` 与 `python -m ruff check` 通过；elevated focused pytest `tests\test_rank_programbench_candidates.py tests\test_plan_official_breakthrough_targets.py` 为 `83 passed`；真实 planner JSON smoke 首行是 `alecthomas__chroma.8d04def`，原因 `official_eval_failed_without_eval_json`。普通 sandbox pytest 仍会在 `C:\tmp` basetemp 报 `WinError 5`，因此需要 elevated focused pytest 才能作为通过证据。本修复未调用外部 Kimi/GLM，未再次执行 official eval，也不是官方 aggregate 突破。
- 2026-05-20 继续复核 `clog-tool__clog-cli.7066cba` patch6，仍按“子代理/LLM 必须放入 ReBuilder 架构内推理”的边界执行，没有使用 Kimi/GLM。主会话在 `output\file_bridge_manual\run_clog_file_bridge.py` 增加 `from_latest_patch6`，修复 patch5 剩余的 visible cleanroom-local outfile padding mismatch，并给 runner 补 `--pull`、`--official-eval`、`--force`。focused harness test `tests\test_clog_file_bridge_harness.py` 为 `1 passed`（需 elevated 避开 Windows basetemp ACL），`py_compile` 与 `python -m ruff check` 通过。本地 no-external `file_bridge` 闭环为 exploration `106/106`、holdout `16/16`、5 个 file_bridge calls；随后显式运行 ProgramBench official aggregate eval，结果 counted `260/575`、score `45`，raw `394/778`、score `51`，与既有 clog score-45 baseline 持平，因此不是 official score breakthrough，也不更新 baseline。困难记录：cleanroom image 起初缺失，旧 runner 没有 `--pull`；sandbox 内 Docker API 管道被拒，需要 elevated Docker；该 patch runtime smoke 只覆盖 args/default/input_files，缺 stdin，所以 strict official-ready ranker 在 `args,input_files,stdin` 维度要求下仍为 `row_count=0`。不要读取或发布 official hidden case 级失败细节。
- 2026-05-20 继续复核 `rbakbashev__elfcat.52f8cc7`，新增 no-external `file_bridge` runner `output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch1` 与 `tests\test_elfcat_file_bridge_harness.py`。该 patch 从公开 cleanroom local evidence 恢复 reference-like HTML shell/byte table/ELF64 metadata 和 Rust-like malformed string-table panic，不使用 Kimi/GLM，也不读取 official hidden case。验证：`py_compile` 通过，`python -m ruff check output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py` 通过，elevated focused pytest `tests\test_elfcat_file_bridge_harness.py` 为 `3 passed`；普通 sandbox pytest 仍被 Windows basetemp ACL `WinError 5` 阻断。ReBuilder local gate 为 exploration `97/119`、holdout `15/18`、runtime smoke 覆盖 args/default/input_files/stdin，package gate 通过但 result 仍 `FAILED`、`almost_resolved=false`。随后执行 ProgramBench official aggregate eval，counted `316/564`、score `56`，raw `390/646`、score `60`，相对本轮前 elfcat score-38 baseline 是 official aggregate baseline upgrade，但不是 solved task；baseline 已更新到 `baselines\programbench\rbakbashev__elfcat.52f8cc7.baseline.json`，submission SHA-256 为 `6c6c56e9837d06dd5e52b8a0c936883a3c2e4504b40f6a8414876d5d0564dddb`。困难记录：strict ranker 在 official eval 前返回 `missing_official_candidate_summary` 是因为已有 baseline upgrades 必须等 official summary 写回；baseline 刷新后再查会返回 `official_not_above_baseline`，表示当前结果已经成为新基线。剩余本地 blockers 仍是 HTML file_output bytes、malformed section-table/range panic shape 和目录输入 errno 差异，不能写成 hidden official failure。

本轮 gate 结果：

- `sd`：历史 no-external-LLM file_bridge subagent best 官方 aggregate 已由 2026-05-21 `baseline_regex_patch1` 刷新为 score 86（699/810 counted；raw 752/869），baseline 已补记；这是同分 counted refinement，不是 score breakthrough 或 solved task。该 patch 修复本地 unclosed-group regex diagnostic 和 bridge runner CRLF/LF 膨胀问题，本地 exploration/holdout 达到 `40/40`、`12/12`；official eval 后 strict gate 对同一候选回落为 `official_not_above_baseline`，不要重复提交。
- `gron`：no-external `file_bridge` patch6 官方 aggregate 已完成，score 62（140/224 counted；raw 148/233），与 baseline 持平，不是突破。
- `nnn`：官方 aggregate baseline 为 score 79（379/477 counted；raw 1101/1796），已回填 summary；仍缺 runtime-smoke/input_files 证据，不是可提交候选。
- `htmlq`：no-external patch3 官方 aggregate 为 score 91，但 counted 1329/1455 低于 baseline 的 1330/1455，不能升级。
- `cmatrix`：no-external file_bridge 候选官方 score 82，低于后续历史 best score 95；score 95 baseline 仍是当前高分记录但未 fully resolved。
- `chroma`：`restore_patch2` 本地 exploration `95/95`、holdout `31/31`、runtime smoke 覆盖 args/stdin/input_files/default，已打包并重跑官方 eval；600 秒 `docker_cpus=4` 和 1800 秒 `docker_cpus=1` bounded eval 均未产出 eval JSON，残留/挂起进程、容器和 matching compiled images 已清理。没有官方分数，不能声明突破。
- `elfcat`：先前 no-external missing-holdout probe 从历史 score-17 升到 score 38；本轮 `reference_html_patch1` 又完成 ProgramBench official aggregate eval，counted `316/564`、score `56`，raw `390/646`、score `60`，相对 score-38 记录是新的 official aggregate baseline upgrade。但 `fully_resolved=false`、`almost_resolved=false`，本地 result 仍 `FAILED`，主要 blockers 仍是 HTML file_output bytes 与 malformed ELF panic shape，因此不是 solved-task breakthrough。
- `go-mod-outdated`：table_patch5 no-external `file_bridge` 官方 aggregate 已完成，score 94（267/285 counted；raw 316/342 score 92），相对 table_patch4 score-80 baseline 是继续升级，但未 fully resolved / almost resolved。
- `zip-password-finder`：usage_patch1 no-external `file_bridge` 官方 aggregate 为 score 36（248/680 counted；raw 340/792），与旧 baseline 持平；后续 usage_patch2 官方 aggregate 升到 score 40（274/680 counted；raw 366/792），是 official aggregate baseline upgrade，但仍不是 solved task。
- `xsv`：restore_patch1 no-external `file_bridge` 官方 aggregate 已完成，score 44（527/1186 counted；raw 604/1317），同分下 counted pass count 高于旧 score-44 记录，但 rounded official score 没提升，不是 score 突破。2026-05-21 `restore_patch2` 又修了本地 frequency/index 行为，本地 exploration `83/102`、holdout `12/15`，但 holdout 未超过历史 best，未进入 official eval。
- `clog-cli`：早期 restore-axis retry 停在 holdout `14/18`，未进入官方 eval；patch5 与 patch6 no-external `file_bridge` 官方 aggregate 均为 score `45`（`260/575` counted；raw `394/778` score `51`），rounded official score 未提升，不是 score breakthrough。patch6 只是把本地 visible outfile mismatch 收敛到 exploration/holdout 100%，并且 runtime-smoke 仍缺 stdin 维度。`csview`：same-axis `restore_patch8` 停在 holdout `8/14` 且缺 `input_files` runtime-smoke 维度；后续 axis-ablation contractfix 完成官方 aggregate upgrade，counted `291/335`、score `87`，但仍不是 solved task。

下一轮不要继续简单增加 repair 次数。implementation 阶段的 Python syntax/CLI dispatch smoke 和 task profile prompt budget 都已有第一版；后续应做小规模 ablation/rerun，验证这些机制是否能改善 xsv/htmlq/gron 等实现阶段失败或 prompt 过载问题，而不是直接进入官方评测。

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

1. 在 strict cleanroom 边界下，完整 reconstruction loop 可以跑通，并且已沉淀多条官方 aggregate baseline，包括 zoxide、cmatrix、chmln sd、nnn、csview、xsv 等任务。
2. 架构层改进确实能解决一些模型单独生成时的失败模式，例如实现阶段截断、shell init 长输出失控、repair 非回归控制和 holdout gate。

但还不能证明：

1. 当前架构已经稳定优于单模型。
2. 最新本地高 exploration 分数代表官方隐藏测试突破。
3. 静态资产带来的收益已经具备跨任务泛化。

下一阶段的核心任务是从“单任务可运行”推进到“多任务可复现、可 ablation、holdout 更强”的研究状态。
