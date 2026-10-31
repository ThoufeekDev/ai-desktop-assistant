"""Background worker for shared JARVIS assistant processing."""

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.assistant_engine import AssistantEngine


class ChatWorker(QObject):
    """Run shared assistant processing outside the GUI thread."""

    succeeded = Signal(str)
    system_action_requested = Signal(str, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        engine: AssistantEngine,
        message: str,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.message = message

    @Slot()
    def run(self) -> None:
        try:
            response = self.engine.process_message(self.message)

            # Notify the GUI before the normal success handler starts speech.
            if response.system_action is not None:
                self.system_action_requested.emit(
                    response.message,
                    response.system_action,
                )

            self.succeeded.emit(response.message)

        except Exception as exc:
            self.failed.emit(str(exc))

        finally:
            self.finished.emit()