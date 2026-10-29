"""Background worker for real JARVIS chat requests."""

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.memory import MemoryStore
from jarvis.ollama_client import OllamaClient


class ChatWorker(QObject):
    """Run memory retrieval and Ollama chat outside the GUI thread."""

    succeeded = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        client: OllamaClient,
        message: str,
    ) -> None:
        super().__init__()
        self.client = client
        self.message = message

    @Slot()
    def run(self) -> None:
        try:
            memory_store = MemoryStore()
            memories = [
                f"Saved fact: {memory.content}"
                for memory in memory_store.search(self.message, limit=5)
            ]

            reply = self.client.chat(
                self.message,
                memories=memories,
            )
            self.succeeded.emit(reply)

        except Exception as exc:
            self.failed.emit(str(exc))

        finally:
            self.finished.emit()
