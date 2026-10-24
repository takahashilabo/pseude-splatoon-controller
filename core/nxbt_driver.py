"""
NXBT (Bluetooth Pro Controller Emulation) Driver
BlueZ経由でSwitchへ直接「プロコン」としてBluetoothペアリングし、
リアルタイムに入力を送信する。SwitchHIDDriverと同じインターフェース(send_state/reset/close)を
持つため、core.passthrough.ControllerPassthroughやweb/app.pyから透過的に差し替えられる。
"""

import logging
import threading
from typing import Optional

from core.controller_state import ControllerState, SwitchButton, SwitchHat

logger = logging.getLogger("NXBTDriver")

try:
    import nxbt
    _NXBT_AVAILABLE = True
except ImportError:
    _NXBT_AVAILABLE = False


# SwitchButton フラグ -> nxbt input_packet のキー名
_BUTTON_KEY_MAP = {
    SwitchButton.Y: "Y",
    SwitchButton.B: "B",
    SwitchButton.A: "A",
    SwitchButton.X: "X",
    SwitchButton.L: "L",
    SwitchButton.R: "R",
    SwitchButton.ZL: "ZL",
    SwitchButton.ZR: "ZR",
    SwitchButton.MINUS: "MINUS",
    SwitchButton.PLUS: "PLUS",
    SwitchButton.HOME: "HOME",
    SwitchButton.CAPTURE: "CAPTURE",
}

# SwitchHat -> (DPAD_UP, DPAD_RIGHT, DPAD_DOWN, DPAD_LEFT)
_HAT_DPAD_MAP = {
    SwitchHat.TOP:          (True, False, False, False),
    SwitchHat.TOP_RIGHT:    (True, True, False, False),
    SwitchHat.RIGHT:        (False, True, False, False),
    SwitchHat.BOTTOM_RIGHT: (False, True, True, False),
    SwitchHat.BOTTOM:       (False, False, True, False),
    SwitchHat.BOTTOM_LEFT:  (False, False, True, True),
    SwitchHat.LEFT:         (False, False, False, True),
    SwitchHat.TOP_LEFT:     (True, False, False, True),
    SwitchHat.CENTER:       (False, False, False, False),
}


class NXBTDriver:
    def __init__(self):
        self.is_mock = not _NXBT_AVAILABLE
        self.is_connected = False
        self._nx: Optional["nxbt.Nxbt"] = None
        self._controller_index: Optional[int] = None

        if self.is_mock:
            logger.info("[*] nxbt パッケージが見つからないため [Mockモード (シミュレーション)] で動作します。")
            return

        try:
            self._nx = nxbt.Nxbt()
            self._controller_index = self._nx.create_controller(
                nxbt.PRO_CONTROLLER,
                reconnect_address=self._nx.get_switch_addresses(),
            )
            threading.Thread(target=self._wait_connection, daemon=True).start()
        except Exception as e:
            logger.warning(f"[!] nxbt の初期化に失敗 ({e})。Mockモードに移行します。")
            self.is_mock = True

    def _wait_connection(self):
        """Switch側の「コントローラー」→「持ち方/順番を変える」画面でペアリングされるまで待機"""
        try:
            logger.info("[*] Switchとのペアリングを待機中です...")
            self._nx.wait_for_connection(self._controller_index)
            self.is_connected = True
            logger.info("[+] Switchとのペアリングが完了しました。")
        except Exception as e:
            logger.error(f"[!] ペアリング待機中にエラー: {e}")

    def send_state(self, state: ControllerState):
        """ControllerStateオブジェクトをnxbtの入力パケットに変換して送信"""
        if self.is_mock or self._nx is None or not self.is_connected:
            return

        packet = self._nx.create_input_packet()

        for flag, key in _BUTTON_KEY_MAP.items():
            if state.buttons & flag:
                packet[key] = True

        up, right, down, left = _HAT_DPAD_MAP[state.hat]
        packet["DPAD_UP"] = up
        packet["DPAD_RIGHT"] = right
        packet["DPAD_DOWN"] = down
        packet["DPAD_LEFT"] = left

        lx = max(-100, min(100, state.lx))
        ly = max(-100, min(100, state.ly))
        rx = max(-100, min(100, state.rx))
        ry = max(-100, min(100, state.ry))

        packet["L_STICK"]["X_VALUE"] = int(lx)
        # チェック画面の上下表示とゲーム内の前進方向は一致しないため、
        # 実際のプレイでの前進方向を基準に反転なしにしている
        packet["L_STICK"]["Y_VALUE"] = int(ly)
        packet["L_STICK"]["PRESSED"] = bool(state.buttons & SwitchButton.LCLICK)

        packet["R_STICK"]["X_VALUE"] = int(rx)
        packet["R_STICK"]["Y_VALUE"] = int(ry)
        packet["R_STICK"]["PRESSED"] = bool(state.buttons & SwitchButton.RCLICK)

        try:
            self._nx.set_controller_input(self._controller_index, packet)
        except Exception as e:
            logger.error(f"NXBT入力送信エラー: {e}")

    def send_imu(self, accel_xyz, gyro_xyz):
        """
        IMU(ジャイロ/加速度)の生データをnxbtへ渡す。
        accel_xyz/gyro_xyzはSwitch側の生単位(1/4096g, 1/14247dps)の整数3要素。
        nxbt_patches/protocol.py の set_imu_samples() 拡張が適用されている
        場合のみ有効 (未適用のnxbtでは何も起きない)。
        """
        if self.is_mock or self._nx is None or self._controller_index is None:
            return
        try:
            samples = list(accel_xyz) + list(gyro_xyz)
            self._nx.manager_state[self._controller_index]["direct_imu"] = samples
        except Exception as e:
            logger.error(f"IMU送信エラー: {e}")

    def reset(self):
        """入力を全てニュートラルに戻す"""
        self.send_state(ControllerState())

    def close(self):
        self.reset()
        if self._nx is not None and self._controller_index is not None:
            try:
                self._nx.remove_controller(self._controller_index)
            except Exception:
                pass
