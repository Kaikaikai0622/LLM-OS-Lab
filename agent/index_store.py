"""
执行结果索引存储系统

支持多种存储后端：
- InMemoryIndexStore: 内存存储（最小实现）
- FileIndexStore: 文件持久化（预留）
- VectorIndexStore: 向量检索（预留）
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from agent.schemas import ExecutionRecord


class IndexStore(ABC):
    """
    索引存储抽象基类

    所有存储后端的统一接口
    """

    @abstractmethod
    def save(self, execution_result: dict) -> str:
        """
        保存执行结果，返回执行ID

        Args:
            execution_result: 原始执行结果字典

        Returns:
            str: 全局唯一的 execution_id
        """
        pass

    @abstractmethod
    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        """
        根据ID获取完整执行记录

        Args:
            execution_id: 执行ID

        Returns:
            ExecutionRecord | None: 记录不存在时返回None
        """
        pass

    @abstractmethod
    def latest(self, limit: int = 5) -> list[ExecutionRecord]:
        """
        获取最近N条执行记录

        Args:
            limit: 返回记录数，默认5条

        Returns:
            list[ExecutionRecord]: 按时间倒序排列的记录列表
        """
        pass


class InMemoryIndexStore(IndexStore):
    """
    内存索引存储实现

    特点：
    - 数据仅在内存中，进程结束即丢失
    - 访问速度快
    - 适合最小Agent验证

    使用示例：
        store = InMemoryIndexStore()
        execution_id = store.save({"status": "success", "stdout": "hello"})
        record = store.get(execution_id)
    """

    def __init__(self):
        # 主存储：execution_id -> ExecutionRecord
        self._records: dict[str, ExecutionRecord] = {}
        # 时间索引：按写入顺序存储ID列表
        self._order: list[str] = []

    def save(self, execution_result: dict) -> str:
        """
        保存执行结果到内存

        自动处理字段兜底：
        - stdout/stderr/result 缺失时补默认值
        - 自动生成 created_at
        """
        # 生成唯一ID
        execution_id = uuid4().hex

        # 字段兜底处理
        sanitized = {
            "execution_id": execution_id,
            "status": execution_result.get("status", "unknown"),
            "stdout": execution_result.get("stdout", "") or "",
            "stderr": execution_result.get("stderr", "") or "",
            "result": execution_result.get("result"),
            "execution_time": execution_result.get("execution_time", 0.0),
            "created_at": execution_result.get("created_at") or datetime.utcnow().isoformat(),
        }

        # 创建记录对象
        record = ExecutionRecord.from_dict(sanitized)

        # 存储
        self._records[execution_id] = record
        self._order.append(execution_id)

        return execution_id

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        """
        根据ID获取记录

        记录不存在时返回None，不抛出异常
        """
        return self._records.get(execution_id)

    def latest(self, limit: int = 5) -> list[ExecutionRecord]:
        """
        获取最近N条记录

        边界处理：
        - limit <= 0 时返回空列表
        - limit 超过总记录数时返回全部
        """
        if limit <= 0:
            return []

        # 从后往前取limit个ID
        recent_ids = self._order[-limit:]
        # 倒序排列（最新的在前）
        recent_ids.reverse()

        # 转换为记录列表
        return [self._records[eid] for eid in recent_ids if eid in self._records]

    def __len__(self) -> int:
        """返回当前存储的记录数"""
        return len(self._records)

    def clear(self) -> None:
        """清空所有记录（测试用）"""
        self._records.clear()
        self._order.clear()


class NoOpIndexStore(IndexStore):
    """
    无索引存储实现（跳过存储）

    特点：
    - save() 仅生成 execution_id，不保存记录
    - get()/latest() 始终返回空结果
    - 用于 baseline：验证“跳过存储”路径
    """
    def __len__(self) -> int:
        """NoOp 模式始终无记录"""
        return 0
    def save(self, execution_result: dict) -> str:
        """生成 execution_id 但不保存 execution_result。"""
        return uuid4().hex

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        """无索引模式下无法回查，固定返回 None。"""
        return None

    def latest(self, limit: int = 5) -> list[ExecutionRecord]:
        """无索引模式下没有历史记录。"""
        return []
