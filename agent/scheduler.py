"""Simple cooperative scheduler for task loops."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, Iterable


class TaskScheduler:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def run(self, tasks: Iterable[Callable[[], None]], *, delay_range: tuple[int, int] = (30, 90)) -> None:
        for task in tasks:
            task()
            wait = random.randint(*delay_range)
            self.logger.debug("Waiting %s seconds before next action", wait)
            time.sleep(wait)
