import json
import time
from datetime import datetime
import random

class BotPhaseController:
    def __init__(self):
        self.phase = 1
        self.phase_start_time = time.time()
        self.phase_durations = {1: 86400, 2: 86400, 3: 604800}  # Phase 1: 24h, Phase 2: 24h, Phase 3: 7 days
        self.config = self.load_config()
    
    def load_config(self):
        return {
            "phase_1": {
                "post_interval_min": 15,
                "post_interval_max": 45,
                "reply_delay_min": 2,
                "reply_delay_max": 8,
                "max_replies_per_hour": 8,
                "max_posts_per_day": 12,
                "link_frequency_min": 0.40,
                "link_frequency_max": 0.60,
                "break_after_actions": 5,
                "break_duration_min": 30,
                "break_duration_max": 60,
                "sleep_hours": (2, 6),
                "chatgpt_temp": 0.6,
                "user_agents": [
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                ]
            },
            "phase_2": {
                "reply_archetypes": {
                    "curious_skeptic": 0.30,
                    "pattern_finder": 0.40,
                    "helper_authority": 0.30
                },
                "link_strategy": "contextual",
                "max_char_length": 200,
                "question_frequency": 0.40,
                "chatgpt_temp": 0.8
            },
            "phase_3": {
                "radar_check_interval": 1800,
                "priority_boost": 2.0,
                "first_mover_window": 300
            },
            "stage_12": {
                "stage12_enabled": True,
                "stage12_hourly_max_replies": 5,
                "stage12_trend_refresh_minutes": 60
            }
        }
    
    def update_phase(self):
        elapsed = time.time() - self.phase_start_time
        if elapsed < self.phase_durations[1]:
            self.phase = 1
        elif elapsed < self.phase_durations[1] + self.phase_durations[2]:
            self.phase = 2
        else:
            self.phase = 3
        return self.phase
    
    def get_phase_config(self):
        phase = self.update_phase()
        if phase == 1:
            return self.config["phase_1"]
        elif phase == 2:
            return {**self.config["phase_1"], **self.config["phase_2"]}
        else:
            return {**self.config["phase_1"], **self.config["phase_2"], **self.config["phase_3"]}

PHASE_CONTROLLER = BotPhaseController()

