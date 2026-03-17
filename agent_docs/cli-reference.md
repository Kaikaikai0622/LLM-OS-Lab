# CLI 命令参考

完整的命令行使用参考。

## 基础命令

```bash
# Quick test
python -m agent "2+2等于多少"

# With options
python -m agent "计算1到100的和" --max-executions 5 --verbose
```

## 三种运行模式

```bash
# Native 模式 - 完整输出
python -m agent "task" --no-index --summary-max-chars 999999

# Baseline 模式 - 截断输出
python -m agent "task" --no-fetch-tool

# Context Mode (默认) - 压缩+索引
python -m agent "task"
```

## 多模型支持

```bash
# 指定模型
python -m agent "task" --model qwen-turbo

# 使用 OpenAI 兼容 API
python -m agent "task" --model gpt-4o-mini \
  --base-url https://api.openai.com/v1 \
  --api-key sk-xxx
```

## 冒烟测试

```bash
# E2E 测试
docker-compose run --rm sandbox python tests/smoke_e2e.py

# 多 tool_calls 测试
docker-compose run --rm sandbox python tests/smoke_phase3_multi_toolcalls.py

# 总超时测试
docker-compose run --rm sandbox python tests/smoke_phase3_total_timeout.py
```

## Benchmark 实验

```bash
# 三模式对比
python main.py --mode native --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/native.json
python main.py --mode baseline --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/baseline.json
python main.py --mode context_mode --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/cm.json

# 多模型对比
python main.py --mode context_mode --model qwen-plus --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/cm_plus.json
python main.py --mode context_mode --model qwen-turbo --task-file experiment_tasks/benchmark_tasks_subset5.txt --log-file logs/cm_turbo.json
```
