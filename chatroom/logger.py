# logger.py -- structured logger used by all modules

import logging
import sys
import time


class _MsecFormatter(logging.Formatter):
    """Formatter that renders milliseconds portably across platforms."""

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        fmt = datefmt or "%H:%M:%S"
        s = time.strftime(fmt, ct)
        return f"{s}.{int(record.msecs):03d}"


def get_logger(name: str, node_id: int) -> logging.Logger:
    logger = logging.getLogger(f"{name}[Node-{node_id}]")
    if not logger.handlers:
        fmt = _MsecFormatter(
            fmt="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s",
            datefmt="%H:%M:%S",
        )

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        # Also write to a per-node log file for verification
        fh = logging.FileHandler(f"node_{node_id}.log", mode="a")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger
