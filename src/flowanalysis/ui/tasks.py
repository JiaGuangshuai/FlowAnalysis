"""Spawned computation keeps expensive algorithms cancellable outside the GUI thread."""
import multiprocessing as mp
import traceback

from PySide6.QtCore import QObject, QTimer, Signal


def _execute(connection, function, args, kwargs):
    try:
        result = function(*args, **kwargs)
        connection.send((True, result))
    except BaseException as error:
        connection.send((False, (str(error), traceback.format_exc())))
    finally:
        connection.close()


class TaskManager(QObject):
    finished = Signal(object)
    failed = Signal(str, str)
    busyChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.connection = None
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)

    @property
    def busy(self):
        return self.process is not None

    def start(self, function, *args, **kwargs):
        if self.busy:
            raise ValueError("Another task is running")
        context = mp.get_context("spawn")
        self.connection, child = context.Pipe(duplex=False)
        self.process = context.Process(target=_execute, args=(child, function, args, kwargs))
        self.process.start()
        child.close()
        self.timer.start()
        self.busyChanged.emit(True)

    def poll(self):
        if not self.process:
            return
        if self.connection.poll():
            try:
                ok, value = self.connection.recv()
            except (EOFError, OSError):
                ok, value = False, ("Worker exited before returning a result", "")
            self.cleanup()
            if ok:
                self.finished.emit(value)
            else:
                self.failed.emit(*value)
        elif not self.process.is_alive():
            code = self.process.exitcode
            self.cleanup()
            self.failed.emit(f"Worker exited with code {code}", "")

    def cleanup(self):
        self.timer.stop()
        if self.process:
            self.process.join(timeout=.1)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=.2)
        if self.connection:
            self.connection.close()
        self.process = self.connection = None
        self.busyChanged.emit(False)

    def cancel(self):
        if self.process:
            self.process.terminate()
            self.cleanup()
