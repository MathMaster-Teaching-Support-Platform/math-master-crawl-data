"""Reduce noise from BE/FE polling lesson pages while OCR runs."""

import logging


class SuppressBookLessonPagePollSuccess(logging.Filter):
    """Hide successful GETs to list/read OCR pages — they flood the console."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        msg = record.getMessage()
        if (
            "GET " in msg
            and "/api/v1/books/" in msg
            and "/lessons/" in msg
            and "/pages" in msg
            and " 200 OK" in msg
        ):
            return False
        return True


def install_access_log_poll_filter() -> None:
    """Attach once after logging is configured."""
    log = logging.getLogger("uvicorn.access")
    if any(isinstance(f, SuppressBookLessonPagePollSuccess) for f in log.filters):
        return
    log.addFilter(SuppressBookLessonPagePollSuccess())
