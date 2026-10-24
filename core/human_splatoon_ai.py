"""
Splatoon Human-like Behavior AI Generator
人間らしい不規則性、行動遷移、指の慣性(Lerp)、手ブレを模倣するAIエンジン
"""

import math
import random
from enum import Enum
from typing import Dict, Any, Optional
from core.controller_state import ControllerState, SwitchButton, SwitchHat


class PlayStyle(Enum):
    BALANCED = "balanced"       # バランス型 (塗り + イカダッシュ + 索敵)
    STEALTH = "stealth"         # 潜伏・慎重型 (センプク長め、索敵多め)
    AGGRESSIVE = "aggressive"   # アグレッシブ型 (射撃多め、ジャンプ撃ち多め)


class ActionState(Enum):
    PAINT_ADVANCE = "インク塗り前進"
    SWIM_DASH     = "イカダッシュ移動"
    SEARCH_LOOK   = "周囲索敵・クリアリング"
    RECOVER_INK   = "センプク潜伏・インク回復"
    COMBAT_EVADE  = "対面ジャンプ撃ち・引き撃ち"


def lerp(current: float, target: float, factor: float) -> float:
    return current + (target - current) * factor


def clamp(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, val))


class HumanSplatoonAI:
    def __init__(self, style: PlayStyle = PlayStyle.BALANCED):
        self.style = style
        self.state = ControllerState()
        
        self.target_lx = 0.0
        self.target_ly = 0.0
        self.target_rx = 0.0
        self.target_ry = 0.0
        
        self.current_action = ActionState.SEARCH_LOOK
        self.action_timer = 0.0
        self.action_duration = 1.0
        
        self._choose_next_action()

    def set_style(self, style: PlayStyle):
        self.style = style

    def _choose_next_action(self):
        """プレイスタイルと直前のアクションに応じて次の行動を選択"""
        if self.style == PlayStyle.STEALTH:
            weights = {
                ActionState.PAINT_ADVANCE: 20,
                ActionState.SWIM_DASH: 25,
                ActionState.SEARCH_LOOK: 25,
                ActionState.RECOVER_INK: 25,
                ActionState.COMBAT_EVADE: 5,
            }
        elif self.style == PlayStyle.AGGRESSIVE:
            weights = {
                ActionState.PAINT_ADVANCE: 35,
                ActionState.SWIM_DASH: 25,
                ActionState.SEARCH_LOOK: 10,
                ActionState.RECOVER_INK: 10,
                ActionState.COMBAT_EVADE: 20,
            }
        else: # BALANCED
            weights = {
                ActionState.PAINT_ADVANCE: 30,
                ActionState.SWIM_DASH: 30,
                ActionState.SEARCH_LOOK: 15,
                ActionState.RECOVER_INK: 15,
                ActionState.COMBAT_EVADE: 10,
            }

        # 行動の自然な連続性
        prev = self.current_action
        if prev == ActionState.PAINT_ADVANCE:
            weights[ActionState.SWIM_DASH] = int(weights[ActionState.SWIM_DASH] * 1.8)
        elif prev == ActionState.SWIM_DASH:
            weights[ActionState.SEARCH_LOOK] = int(weights[ActionState.SEARCH_LOOK] * 1.5)
            weights[ActionState.PAINT_ADVANCE] = int(weights[ActionState.PAINT_ADVANCE] * 1.4)

        actions = list(weights.keys())
        w_vals = list(weights.values())
        next_act = random.choices(actions, weights=w_vals)[0]
        self.current_action = next_act

        # ガウス分布による人間らしい持続時間の揺らぎ
        durations = {
            ActionState.PAINT_ADVANCE: random.gauss(2.2, 0.4),
            ActionState.SWIM_DASH: random.gauss(1.8, 0.3),
            ActionState.SEARCH_LOOK: random.gauss(1.2, 0.25),
            ActionState.RECOVER_INK: random.gauss(1.6, 0.35),
            ActionState.COMBAT_EVADE: random.gauss(1.7, 0.3),
        }
        self.action_duration = max(0.5, durations[next_act])
        self.action_timer = 0.0

        # 行動に応じたターゲット初期化
        self._init_action_targets(next_act)

    def _init_action_targets(self, action: ActionState):
        self.state.buttons = SwitchButton.NONE

        if action == ActionState.PAINT_ADVANCE:
            self.target_ly = random.uniform(70.0, 100.0)
            self.target_lx = random.uniform(-25.0, 25.0)
            self.target_rx = random.uniform(-40.0, 40.0)
            self.target_ry = 0.0
            self.state.set_button(SwitchButton.ZR, True) # 射撃

        elif action == ActionState.SWIM_DASH:
            angle = random.uniform(-math.pi / 3, math.pi / 3)
            self.target_lx = math.sin(angle) * 100.0
            self.target_ly = math.cos(angle) * 100.0
            self.target_rx = 0.0
            self.target_ry = 0.0
            self.state.set_button(SwitchButton.ZL, True) # 潜伏
            if random.random() < 0.25:
                self.state.set_button(SwitchButton.B, True) # イカロール/ジャンプ

        elif action == ActionState.SEARCH_LOOK:
            self.target_lx = random.uniform(-20.0, 20.0)
            self.target_ly = random.uniform(-10.0, 20.0)
            self.target_rx = random.choice([-1, 1]) * random.uniform(40.0, 80.0)
            self.target_ry = random.uniform(-10.0, 10.0)
            if random.random() < 0.4:
                self.state.set_button(SwitchButton.ZL, True)

        elif action == ActionState.RECOVER_INK:
            self.target_lx = random.uniform(-5.0, 5.0)
            self.target_ly = random.uniform(-5.0, 5.0)
            self.target_rx = 0.0
            self.target_ry = 0.0
            self.state.set_button(SwitchButton.ZL, True)

        elif action == ActionState.COMBAT_EVADE:
            self.target_lx = random.choice([-1, 1]) * random.uniform(60.0, 100.0)
            self.target_ly = random.uniform(0.0, 40.0)
            self.target_rx = random.uniform(-30.0, 30.0)
            self.state.set_button(SwitchButton.ZR, True)
            self.state.set_button(SwitchButton.B, True)

    def update(self, dt: float) -> ControllerState:
        """フレーム毎の更新 (20〜50fps)"""
        self.action_timer += dt
        if self.action_timer >= self.action_duration:
            self._choose_next_action()

        action = self.current_action

        # 塗り中のカメラの左右サイン波スイング
        if action == ActionState.PAINT_ADVANCE:
            swing = math.sin(self.action_timer * 4.5) * 35.0
            self.target_rx = swing

        # ジャンプ撃ち時のジャンプボタン点滅
        if action == ActionState.COMBAT_EVADE:
            jump_active = (int(self.action_timer * 3.5) % 2 == 0)
            self.state.set_button(SwitchButton.B, jump_active)

        # 人間の微小な手ブレノイズ
        noise_lx = random.gauss(0, 1.5)
        noise_ly = random.gauss(0, 1.5)
        noise_rx = random.gauss(0, 2.0)

        # 指の慣性による補間 (急激な入力を防ぐ)
        lerp_rate = 0.22
        self.state.lx = clamp(lerp(self.state.lx, self.target_lx + noise_lx, lerp_rate), -100, 100)
        self.state.ly = clamp(lerp(self.state.ly, self.target_ly + noise_ly, lerp_rate), -100, 100)
        self.state.rx = clamp(lerp(self.state.rx, self.target_rx + noise_rx, lerp_rate), -100, 100)
        self.state.ry = clamp(lerp(self.state.ry, self.target_ry, lerp_rate), -100, 100)

        return self.state

    def get_status_dict(self) -> Dict[str, Any]:
        """Web UI用のステータス辞書"""
        return {
            "action_name": self.current_action.value,
            "style": self.style.value,
            "remaining_sec": round(max(0.0, self.action_duration - self.action_timer), 1),
            "lx": round(self.state.lx, 1),
            "ly": round(self.state.ly, 1),
            "rx": round(self.state.rx, 1),
            "ry": round(self.state.ry, 1),
            "zr": bool(self.state.buttons & SwitchButton.ZR),
            "zl": bool(self.state.buttons & SwitchButton.ZL),
            "b": bool(self.state.buttons & SwitchButton.B),
        }
