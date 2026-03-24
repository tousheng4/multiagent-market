import asyncio
from typing import Any, Callable, List, Optional, Type

from beanie import Document

from agents.memory.memoryModels import MemoryEntry

from .MemoryConnector import MemoryConnector


class MongoConnector(MemoryConnector):
    """
    Beanie (MongoDB ODM) 版 Connector。
    通过 runner 让异步 Beanie 在当前同步上下文里执行。
    """

    def __init__(
        self,
        document_model: Type[Document],
        runner: Optional[Callable[[Any], Any]] = None,
    ):
        self.document_model = document_model
        self.runner = runner

    def _run(self, coro: Any):
        if self.runner:
            return self.runner(coro)
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            raise RuntimeError(
                "An event loop is already running; provide a runner to MongoConnector for Beanie operations."
            ) from exc

    def _doc_to_dict(self, doc: Any) -> dict:
        if hasattr(doc, "model_dump"):
            return doc.model_dump()
        if hasattr(doc, "dict"):
            return doc.dict()
        return dict(doc)

    def append(self, entry: MemoryEntry) -> None:
        doc = self.document_model(**entry.to_storage_record(include_datetime=True))
        self._run(doc.insert())

    def recent(self, agent_id: str, limit: int = 100) -> List[MemoryEntry]:
        query = (
            self.document_model.find(self.document_model.agentId == agent_id)
            .sort("-timestamp")
            .limit(limit)
        )
        docs = self._run(query.to_list())
        return [MemoryEntry.from_record(self._doc_to_dict(doc)) for doc in docs]
