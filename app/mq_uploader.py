"""消息队列上传器 — MT/T 1201.2-2023

队列命名规范：monitordata__系统简称__分类
示例：monitordata__tfjk__fanrealdata

支持后端：
- rabbitmq (需要 aio-pika)
- 本地日志 (默认，用于调试)
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class MQBackend(ABC):
    """消息队列后端抽象接口"""

    @abstractmethod
    async def connect(self, url: str) -> None: ...

    @abstractmethod
    async def publish(self, queue_name: str, message: str) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...


class LogMQBackend(MQBackend):
    """日志模式消息队列（调试用，无需外部服务）"""

    def __init__(self, log_dir: str = "data/mq_log"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._connected = False

    async def connect(self, url: str) -> None:
        self._connected = True
        logger.info("LogMQ connected (log dir: %s)", self._log_dir)

    async def publish(self, queue_name: str, message: str) -> bool:
        if not self._connected:
            logger.error("LogMQ not connected")
            return False

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{queue_name}_{timestamp}.txt"
        filepath = self._log_dir / filename

        try:
            filepath.write_text(message, encoding="utf-8")
            logger.info("Published to %s -> %s", queue_name, filepath)
            return True
        except Exception:
            logger.exception("Failed to publish to %s", queue_name)
            return False

    async def disconnect(self) -> None:
        self._connected = False


class RabbitMQBackend(MQBackend):
    """RabbitMQ 消息队列后端"""

    def __init__(self):
        self._connection = None
        self._channel = None

    async def connect(self, url: str) -> None:
        try:
            import aio_pika
            self._connection = await aio_pika.connect_robust(url)
            self._channel = await self._connection.channel()
            logger.info("RabbitMQ connected: %s", url)
        except ImportError:
            logger.error("aio-pika not installed. Run: uv add aio-pika")
            raise
        except Exception:
            logger.exception("RabbitMQ connection failed")
            raise

    async def publish(self, queue_name: str, message: str) -> bool:
        if not self._channel:
            logger.error("RabbitMQ not connected")
            return False

        try:
            import aio_pika
            await self._channel.declare_queue(queue_name, durable=True)
            await self._channel.default_exchange.publish(
                aio_pika.Message(body=message.encode("utf-8")),
                routing_key=queue_name,
            )
            logger.info("Published to RabbitMQ queue: %s", queue_name)
            return True
        except Exception:
            logger.exception("Failed to publish to %s", queue_name)
            return False

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None


# ──────────── 队列名映射 ────────────

# MT/T 1201.2-2023 标准队列名
QUEUE_MAP = {
    "jbsj":  "monitordata__jbsj__deviceinfo",
    "absj":  "monitordata__absj__certificateinfo",
    "jztt":  "monitordata__jztt__obsoleteinfo",
    "jcjy":  "monitordata__jcjy__testinfo",
    "tfjc":  "monitordata__tfjk__fandefine",
    "tfss":  "monitordata__tfjk__fanrealdata",
    "tfyc":  "monitordata__tfjk__fanalarmdata",
    "psjc":  "monitordata__psjk__draindefine",
    "psss":  "monitordata__psjk__drainrealdata",
    "psyc":  "monitordata__psjk__drainalarmdata",
    "ljjc":  "monitordata__ljjk__shaftdefine",
    "ljss":  "monitordata__ljjk__shaftrealdata",
    "ljyc":  "monitordata__ljjk__shaftalarmdata",
    "xjjc":  "monitordata__xjjk__slopedefine",
    "xjss":  "monitordata__xjjk__sloperealdata",
    "xjyc":  "monitordata__xjjk__slopealarmdata",
    "kyjc":  "monitordata__kyjk__compressordefine",
    "kyss":  "monitordata__kyjk__compressorrealdata",
    "kyyc":  "monitordata__kyjk__compressoralarmdata",
    "jcjc":  "monitordata__jcjk__hoisterdefine",
    "jcss":  "monitordata__jcjk__hoisterrealdata",
    "jcyc":  "monitordata__jcjk__hoisteralarmdata",
}


class MQUploader:
    """消息队列上传管理器"""

    def __init__(self, backend: MQBackend):
        self._backend = backend
        self._connected = False

    async def connect(self, url: str = "") -> None:
        await self._backend.connect(url)
        self._connected = True

    async def publish_report(self, data_type: str, content: str) -> bool:
        """发布报文到对应队列"""
        queue_name = QUEUE_MAP.get(data_type.lower())
        if not queue_name:
            logger.error("Unknown data type: %s", data_type)
            return False

        return await self._backend.publish(queue_name, content)

    async def publish_all(self, reports: dict[str, str]) -> dict[str, bool]:
        """批量发布报文

        Args:
            reports: {data_type: content} 字典
        Returns:
            {data_type: success} 字典
        """
        results = {}
        for data_type, content in reports.items():
            results[data_type] = await self.publish_report(data_type, content)
        return results

    async def disconnect(self) -> None:
        await self._backend.disconnect()
        self._connected = False


# ──────────── 便捷工厂 ────────────

def create_mq_uploader(backend_type: str = "log", **kwargs) -> MQUploader:
    """创建消息队列上传器

    Args:
        backend_type: "log" (默认) 或 "rabbitmq"
    """
    if backend_type == "rabbitmq":
        backend = RabbitMQBackend()
    else:
        backend = LogMQBackend(log_dir=kwargs.get("log_dir", "data/mq_log"))

    return MQUploader(backend)
