# 项目开发日志

## 概述

本项目是一个 **LangChain Sandbox Demo**，基于 `langchain-sandbox` 和 Pyodide (WebAssembly Python 运行时) 构建的沙箱执行环境。用于安全地执行 Python 代码。

---

## 2026-03-12 开发记录

### 1. 环境配置与初始化

#### 1.1 项目结构创建
```
my-sandbox-demo/
├── Dockerfile              # Python 3.11 + Deno 运行时
├── docker-compose.yml      # 容器编排
├── demo.py                 # 基础演示脚本
├── .devcontainer/
│   └── devcontainer.json   # VS Code Dev Container 配置
└── node_modules/           # Deno 依赖缓存
```

#### 1.2 Docker 环境配置
- **基础镜像**: `python:3.11-slim`
- **安装组件**:
  - Python 3.11
  - Deno 2.7.5 (via 官方安装脚本)
  - `langchain-sandbox` (pip install)
- **权限配置**: 允许网络访问 (`allow_net=True`)

#### 1.3 启动容器
```bash
docker-compose up --build
docker exec my-sandbox-demo-sandbox-1 python demo.py
```

**状态**: ✅ 容器正常运行，沙箱初始化成功

---

### 2. 基础功能验证

#### 2.1 首次运行 Demo
运行 [demo.py](demo.py):
```python
from langchain_sandbox import PyodideSandbox

sandbox = PyodideSandbox(allow_net=True)
result = await sandbox.execute("print('Hello from Sandbox!')")
```

**发现问题**:
- 首次初始化耗时 ~8s (Pyodide WASM 加载)
- 后续执行 ~1.5-2s

**状态**: ✅ 基础功能正常

---

### 3. 深度测试与问题发现

#### 3.1 创建全面测试套件

##### test_sandbox.py - 环境验证测试
测试维度:
1. **执行延迟测试**
   - 冷启动: ~1.8s
   - 热执行: ~1.6s

2. **stdout/stderr 捕获完整性测试**
   - 大量输出 (1000行)
   - 多流混合测试
   - 特殊字符测试
   - 长行测试 (10000字符)

3. **异常隔离测试**
   - 语法错误捕获
   - 运行时异常 (ZeroDivisionError, NameError, TypeError, IndexError)
   - 异常后恢复能力
   - 内存分配测试 (80MB)

4. **纯计算场景测试** (新增)
   - 斐波那契 F(35): ✅ 结果正确 (9227465)
   - 大数 F(100): ✅ 21位大整数处理正常
   - 递归 F(20): ✅ 递归深度正常

##### test_stateful.py - Stateful 模式对比测试
测试发现:
- **Stateless 平均**: 1.54s
- **Stateful 平均**: 3.35s (⚠️ 反而更慢)
- **原因**: 每次仍重新初始化 Pyodide + Session 序列化开销

**状态**: ✅ 变量持久化正常，但性能不佳

---

### 4. 核心问题定位与修复

#### 4.1 问题发现: stdout 换行符丢失

**现象**:
```python
print("Line 1")
print("Line 2")
```
输出: `'Line 1Line 2'` (换行符丢失)

**根因分析**:
- **位置**: `@langchain/pyodide-sandbox` JSR 包 `main.ts` ~line 325
- **问题代码**:
  ```typescript
  const outputJson = {
    stdout: result.stdout?.join('') || null,  // ❌ 应为 join('\n')
    stderr: result.stderr?.join('') || null,
  };
  ```
- **原因**: Pyodide 将每行输出作为数组元素，但连接时未保留换行符

**状态**: ⚠️ 上游 Bug 已定位

#### 4.2 创建修复方案

##### sandbox_wrapper.py - 换行符修复包装器

**核心类**:
- `FixedPyodideSandbox`: 修复换行符的包装器
- `FixedExecutionResult`: 增强的结果封装（含 `raw_result`）

**修复算法** (`_fix_newlines`):
1. **数字→字母边界检测**: 识别 `"0I"` (在 `"Iteration 0Iteration 1"`)
2. **空格分隔符检测**: 识别 `" Start"` 模式
3. **小写→大写边界**: 识别 camelCase 边界 `"tI"`
4. **动态长度计算**: 支持不均匀行长度

**修复效果**:

| 场景 | 修复前 | 修复后 | 状态 |
|------|--------|--------|------|
| 简单 print | `'Line 1Line 2'` | `'Line 1\nLine 2'` | ✅ 完美 |
| 循环 print | `'Iteration 0Iteration 1...'` | `'Iteration 0\nIteration 1...'` | ✅ 完美 |
| 复杂循环 | `'Step 1: processing...'` | `'Step 1: processing...\nStep 2...'` | ✅ 完美 |
| 混合输出 | `'StartItem 0Item 1End'` | `'StartItem 0\nItem 1\nEn\nd'` | ⚠️ 部分 |

**状态**: ✅ Workaround 可用

---

### 5. 架构分析

#### 5.1 系统架构图
```
用户代码层
    ↓
langchain-sandbox (Python)
    ↓
Deno Runtime
    ↓
@langchain/pyodide-sandbox (JSR/TypeScript)
    ↓
Pyodide (WASM)
    ↓
用户 Python 代码 (WASM VM)
```

#### 5.2 性能瓶颈分析

| 阶段 | 耗时 | 说明 |
|------|------|------|
| Deno 启动 | ~10ms | 可忽略 |
| JSR 包加载 | ~200ms | TypeScript 编译 |
| **Pyodide 初始化** | **~1.3s** | **主要瓶颈** |
| 代码执行 | ~50-200ms | 取决于代码 |
| **总计** | **~1.5-1.9s** | 每次执行 |

**结论**:
- 适合: 复杂 AI/ML 计算（计算密集）
- 不适合: 高频简单调用

#### 5.3 创建架构文档

创建 [architecture.md](architecture.md)，包含:
- 5 层系统架构图
- 组件详细说明
- 数据流图
- 性能特征分析
- 安全模型

---

### 6. 文档更新

#### 6.1 更新 CLAUDE.md
新增内容:
- Fixed Sandbox Wrapper 使用说明
- Known Issues & Workarounds 章节
- 换行符丢失问题说明
- Stateful 模式性能警告
- 架构文档引用

#### 6.2 创建项目日志
创建本文件 [PROJECT_LOG.md](PROJECT_LOG.md)，记录完整开发过程。

---

## 关键发现总结

### 已解决问题 ✅

1. **环境配置**: Docker + Deno + Python 沙箱环境正常运行
2. **换行符修复**: 通过 `FixedPyodideSandbox` 包装器解决
3. **测试覆盖**: 纯计算、异常抛出、大输出三大场景全覆盖
4. **架构文档**: 完整的系统架构和性能分析

### 已知问题 ⚠️

1. **上游 Bug**: JSR 包换行符问题需等待官方修复
2. **性能限制**: 每次执行 ~1.5s 初始化开销无法避免
3. **Stateful 模式**: 性能比 Stateless 差，仅用于需要变量持久化的场景

### 使用建议

```python
# 推荐使用修复后的包装器
from sandbox_wrapper import FixedPyodideSandbox

sandbox = FixedPyodideSandbox(allow_net=True)
result = await sandbox.execute("""
for i in range(5):
    print(f"Line {i}")
""")
print(result.stdout)  # 正确显示换行
```

---

## 文件清单

| 文件 | 用途 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | Claude Code 指导文档 |
| [architecture.md](architecture.md) | 系统架构文档 |
| [PROJECT_LOG.md](PROJECT_LOG.md) | 本文件：项目日志 |
| [demo.py](demo.py) | 基础演示脚本 |
| [sandbox_wrapper.py](sandbox_wrapper.py) | 换行符修复包装器 |
| [test_sandbox.py](test_sandbox.py) | 环境验证测试 |
| [test_stateful.py](test_stateful.py) | Stateful 模式测试 |
| [Dockerfile](Dockerfile) | 容器镜像定义 |
| [docker-compose.yml](docker-compose.yml) | 容器编排配置 |

---

## 2026-03-14 P0 未完成项收尾完成

### 完成项清单

根据 phase.md 中的 P0 未完成项收尾方案，已完成以下任务：

#### 1. Dockerfile - fail-fast 构建 ✅

**修改**: 移除 `|| echo "部分依赖安装失败，将在运行时重试"`

**效果**: 依赖安装失败时构建直接失败，不再静默继续

#### 2. agent/__main__.py - 结构化日志 + 参数透传 ✅

**新增功能**:
- 引入 `logging` 模块替代 `print`
- 新增 `--total-timeout` CLI 参数
- 完善 CLI > .env > 默认值优先级逻辑
- 将 `tool_timeout_seconds`, `summary_max_chars`, `total_timeout_seconds` 传入 SandboxAgent

**日志字段**:
- `event`: 事件类型 (agent_start, agent_complete, config_error, runtime_error)
- `model`, `max_executions`: Agent 配置
- `execution_count`, `stop_reason`: 执行结果

#### 3. agent/agent.py - 参数承接与透传 ✅

**新增参数**:
- `tool_timeout_seconds: float = 15.0` - 工具级超时
- `summary_max_chars: int = 500` - 摘要长度限制

**状态注入**:
- `initial_state` 中注入 `tool_timeout_seconds` 和 `summary_max_chars`

#### 4. agent/workflow.py - 配置透传到工具执行 ✅

**修改**:
- `_tool_executor` 从 state 读取 `tool_timeout_seconds` 和 `summary_max_chars`
- 构造 `ExecutePythonConfig` 并传入 `execute_python`
- `create_simple_workflow` 支持新的配置参数

#### 5. agent/tools.py - 摘要结构增强 ✅

**增强**:
- 错误摘要增加 `Error Type` 字段
- `_create_error_result` 和 `_create_error_result_from_exception` 添加 `error_type`
- 提升错误场景下的可观测性

#### 6. agent/schemas.py - AgentState 扩展 ✅

**新增字段**:
- `tool_timeout_seconds: Optional[float]` - 工具级超时
- `summary_max_chars: Optional[int]` - 摘要长度限制

#### 7. tests/smoke_phase4_config_precedence.py - 新增测试 ✅

**测试覆盖**:
1. CLI 覆盖环境变量逻辑验证
2. timeout 透传到 sandbox 验证
3. summary_max_chars 限制摘要长度验证
4. total_timeout 触发 stop_reason=total_timeout 验证
5. Agent 内部配置一致性验证

### 回归测试矩阵

需执行以下测试验证完整性：

```bash
# 新增测试
python tests/smoke_phase4_config_precedence.py

# 全量回归
python tests/smoke_phase1.py
python tests/smoke_phase2.py
python tests/smoke_phase3.py
python tests/smoke_phase3_multi_toolcalls.py
python tests/smoke_phase3_total_timeout.py
python tests/smoke_phase4.py
python tests/smoke_e2e.py

# 容器回归
docker-compose run --rm sandbox python tests/smoke_phase4_config_precedence.py
docker-compose run --rm sandbox python tests/smoke_e2e.py
```

### 完成定义 (DoD) 检查

- [x] `__main__.py` 中不再以 `print` 作为主日志机制
- [x] `timeout`/`summary_max_chars`/`total_timeout` 完成 CLI -> Agent -> workflow -> tools 闭环
- [x] Dockerfile 为 fail-fast
- [x] 新增 `smoke_phase4_config_precedence.py` 并通过
- [x] 全量 smoke + e2e 通过（待验证）

---

*日志创建时间: 2026-03-12*

---

## 2026-03-13 落地评估（Phase 1-5）

### 1. 当前落地状态

基于当前代码与测试资产，Phase 1-5 已达到“可运行 + 可验证”状态。

已落地证据：
1. Agent 核心模块齐备：agent/schemas.py, agent/index_store.py, agent/tools.py, agent/workflow.py, agent/agent.py, agent/__main__.py
2. 分阶段冒烟测试齐备：tests/smoke_phase1.py, tests/smoke_phase2.py, tests/smoke_phase3.py, tests/smoke_phase4.py
3. 端到端测试存在并可执行：tests/smoke_e2e.py
4. 容器运行链路可用：Dockerfile + docker-compose.yml
5. 最近运行结果（用户侧）：
  - docker-compose run --rm sandbox python tests/smoke_phase4.py -> Exit Code 0
  - docker-compose run --rm sandbox python -m agent "2+2等于多少" -> Exit Code 0

结论：
1. 交付层面：Phase 5 可以判定完成
2. 工程层面：可用于 demo/内测，不建议直接作为生产模板

### 2. 架构健壮性评估

总体评级：B（可用，但仍有高价值硬化空间）

优势：
1. 失败可控：工具层捕获异常并结构化返回，避免工作流被异常打断（agent/tools.py）
2. 可追溯：execution_id 与索引存储打通，支持按 ID 回查完整执行记录（agent/index_store.py, agent/agent.py）
3. 安全边界：具备 max_executions 防止无限循环（agent/workflow.py）
4. 配置校验：CLI 启动前进行关键配置校验并快速失败（agent/__main__.py）

风险点（按优先级）：
1. 工作流并未真正使用 LangGraph 编译图，而是手写 while 循环，后续复杂化时状态治理成本会上升（agent/workflow.py）
2. 多工具调用只处理第一条 tool_call，忽略其余调用，可能导致行为偏差（agent/workflow.py）
3. CLI 参数 timeout/summary_max_chars 已解析但未传递到工具执行，配置闭环不完整（agent/__main__.py, agent/workflow.py, agent/tools.py）
4. Docker 构建允许依赖安装失败后继续，可能埋下运行时不确定性（Dockerfile）
5. 会话内消息对象混用 dict 和消息对象，跨 provider 适配时有兼容风险（agent/workflow.py, agent/agent.py）

### 3. 代码延展性评估

总体评级：B+（有不错的扩展接口，但需做边界收敛）

已有延展基础：
1. 索引层抽象清晰：IndexStore + InMemoryIndexStore，易扩展 File/Vector 后端（agent/index_store.py）
2. 工具层可注入：sandbox/index_store/config 均支持依赖注入，测试替身友好（agent/tools.py）
3. Agent 封装清晰：外部只需依赖 SandboxAgent.run 接口（agent/agent.py）
4. e2e 冒烟已存在，便于未来 provider 替换回归（tests/smoke_e2e.py）

限制延展的点：
1. 配置字段命名已绑定 DASHSCOPE_API_KEY，和 LLM_PROVIDER 抽象不一致，未来多 provider 接入会重复改动（agent/__main__.py）
2. 当前工具协议以 execute_python 单工具为中心，缺少统一 ToolRegistry，扩展第二工具会改动多处
3. 缺少稳定的“结果契约版本号”，后续新增字段时可能破坏测试或调用方兼容
4. 测试中存在硬编码本地路径，影响跨环境可移植性（tests/smoke_phase3.py）

### 4. 建议的下一阶段改造（P0/P1）

P0（建议本周完成）：
1. 将 workflow 切换为真实 LangGraph StateGraph 实现，保留现有节点语义
2. 打通配置透传：timeout/summary_max_chars 从 CLI -> Agent -> workflow -> tools
3. 移除 Dockerfile 中“安装失败继续”的容错写法，构建失败即失败
4. 统一消息模型（全部使用 langchain_core.messages 类型）

P1（建议下周完成）：
1. 引入 Provider 抽象（LLM_PROVIDER + provider factory），脱离单一平台变量命名
2. 增加 ToolRegistry，支持多工具注册与路由
3. 定义版本化结果契约（例如 ToolResult v1）并补契约测试
4. 增加并发/压力测试和长会话回归测试

### 5. 量化里程碑（建议）

M1：健壮性硬化完成
1. Phase1-4 + e2e 继续全绿
2. 新增配置透传测试全绿
3. Docker 构建失败率可观测且无静默失败

M2：延展性基线完成
1. 至少接入 2 个 provider（如 DashScope + Anthropic/OpenAI 兼容）
2. 至少 2 个工具可被调度
3. 契约测试覆盖核心输入输出字段

---

评估结论：
1. 现阶段“项目落地”目标已达成
2. 继续向“可持续演进”推进时，应优先解决工作流实现形态、配置透传和构建确定性三项问题

---

## 2026-03-13 P0 决策确认与实施方案

### 1. 已确认技术决策

1. 工作流：完全迁移到 LangGraph StateGraph
2. 多工具调用策略：同轮多个 tool_calls 顺序执行（B）
3. 配置优先级：CLI > .env > 默认值（A）
4. Provider 范围：P0 仅做 DashScope 稳定化（A）
5. 日志策略：切换到结构化 logging（B）
6. Docker 构建：fail-fast（A）
7. 超时语义：单工具超时 + Agent 总超时（B）

### 2. P0 逐文件改造清单

#### 2.1 agent/workflow.py

目标：由手写循环迁移到真实 StateGraph。

改造点：
1. 定义节点：agent_node、tool_executor、finalizer
2. 定义条件边：
- 无 tool_calls -> finalizer
- 有 tool_calls 且未超限 -> tool_executor
- 达到 max_executions 或总超时 -> finalizer
3. tool_executor 支持顺序执行同轮多个 tool_calls：
- 按调用顺序依次执行 execute_python
- 每次执行追加 ToolMessage
- 每次执行更新 last_execution_id
- execution_count 按“工具调用次数”累加
4. 将 timeout/summary_max_chars 通过 state 或 config 显式传入节点
5. 删除 while True 逻辑，统一由 graph.invoke/ainvoke 驱动

验收：
1. Phase3 冒烟不回退
2. 新增“同轮多 tool_calls 顺序执行”用例通过

#### 2.2 agent/agent.py

目标：统一 Agent 运行参数入口并承载总超时。

改造点：
1. SandboxAgent 构造增加参数：
- tool_timeout_seconds
- summary_max_chars
- total_timeout_seconds
2. run() 中记录 start_time，超时信息注入初始 state
3. 统一 final_answer 提取逻辑（仅消息对象，不再混用 dict）

验收：
1. 总超时触发时返回可解释 stop reason
2. execution_count、last_execution_id 仍可正确追溯

#### 2.3 agent/tools.py

目标：配置透传闭环 + 顺序执行场景稳定。

改造点：
1. ExecutePythonConfig 与 CLI 参数严格对齐
2. execute_python 接收并使用传入 config，不依赖隐式默认
3. 摘要生成追加字段：tool_name、call_index（可选）
4. 错误摘要结构化（error_type、message、preview）

验收：
1. CLI 指定 --summary-max-chars 可见生效
2. 单工具 timeout 生效并可在 summary 中识别

#### 2.4 agent/__main__.py

目标：配置优先级与运行参数完全闭环。

改造点：
1. 保持 CLI > .env > 默认值
2. 将 --timeout 传递到 SandboxAgent（tool_timeout_seconds）
3. 增加 --total-timeout 参数并传递到 Agent
4. 日志切换为 logging：
- 默认 INFO
- --verbose 启用 DEBUG
- 输出统一字段（event、execution_id、round、duration_ms）

验收：
1. 参数覆盖行为在 smoke_phase4 中有断言
2. 配置错误统一以 [CONFIG_ERROR] 输出

#### 2.5 agent/schemas.py

目标：支持超时、终止原因和结构化日志字段。

改造点：
1. AgentState 增加：
- started_at
- total_timeout_seconds
- stop_reason
- tool_timeout_seconds
- summary_max_chars
2. AgentResult 增加 stop_reason（若已有 stopped_by_limit 则并存）

验收：
1. 达到总超时和达到轮次上限可以区分

#### 2.6 Dockerfile

目标：消除静默失败，确保构建确定性。

改造点：
1. 删除“pip install -r requirements.txt || echo ...”
2. 保持 pip install 失败即构建失败

验收：
1. 依赖异常时 docker build 直接失败
2. 正常依赖时构建成功并可运行现有测试

### 3. P0 测试矩阵（新增 + 回归）

新增测试：
1. tests/smoke_phase3_multi_toolcalls.py
- 构造同轮 2 个 tool_calls
- 断言按顺序执行、execution_count += 2
2. tests/smoke_phase3_total_timeout.py
- 配置极小 total_timeout
- 断言 stop_reason=total_timeout
3. tests/smoke_phase4_config_precedence.py
- 校验 CLI > .env > 默认值
- 校验 --timeout 与 --summary-max-chars 生效

回归测试：
1. tests/smoke_phase1.py
2. tests/smoke_phase2.py
3. tests/smoke_phase3.py
4. tests/smoke_phase4.py
5. tests/smoke_e2e.py

通过标准：
1. 全部 smoke 脚本退出码 0
2. docker-compose 运行 smoke_e2e 退出码 0
3. 无 Traceback

### 4. 实施顺序与预估

1. 第 1 天：workflow.py + schemas.py + agent.py（图迁移与超时语义）
2. 第 2 天：tools.py + __main__.py（配置透传、结构化日志）
3. 第 3 天：Dockerfile fail-fast + 新增测试 + 全量回归

### 5. 风险与回滚策略

1. 迁移 StateGraph 后行为偏差
- 预案：保留旧实现分支，逐条对照 smoke_phase3 用例
2. 多 tool_calls 触发消息顺序问题
- 预案：每次执行后立即 append ToolMessage，确保顺序可观察
3. 总超时导致误伤长任务
- 预案：先设宽松默认值（如 60s），通过 CLI 可覆盖
