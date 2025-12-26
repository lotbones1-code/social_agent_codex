from __future__ import annotations

import random
import time
from typing import Callable

from .config import AgentConfig


class Scheduler:
    """Simple loop controller that spaces out actions."""

    def __init__(self, config: AgentConfig):
        self.config = config

    def between_actions(self) -> None:
        delay = random.uniform(self.config.action_delay_min, self.config.action_delay_max)
        time.sleep(delay)

    def between_cycles(self) -> None:
        time.sleep(self.config.loop_delay_seconds)

    def run_forever(self, task: Callable[[], None]) -> None:
        while True:
            task()
            self.between_cycles()


__all__ = ["Scheduler"]
