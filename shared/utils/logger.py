import logging
from logging.handlers import RotatingFileHandler


def setup_logger(app, log_name="App.log"):
    """
    log_name should be distinct per Flask process (e.g. "App_management.log"
    vs "App_teacher.log"). The management and teacher apps run as separate
    processes but historically both pointed at the same literal "App.log" -
    fine for one app alone, but when both run at once from the same folder,
    each process's RotatingFileHandler fights the other for the same file.
    On Windows in particular, rotating (renaming App.log -> App.log.1) fails
    with PermissionError if the *other* process still has that same file
    open, since Windows won't let you rename a file another process holds.
    Giving each app its own log file avoids the cross-process collision
    entirely.
    """
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    handler = RotatingFileHandler(
        log_name,
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=5
    )

    handler.setFormatter(formatter)

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
