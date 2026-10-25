"""
Nintendo Switch Controller Passthrough Engine
---------------------------------------------
本物のプロコンからの入力を /dev/input/js0 経由でリアルタイムに読み取り、
遅延なくそのまま Switch (USB HID /dev/hidg0) へ中継（素通り）させます。

スマホから「START BOT」が押されると、プロコンの入力をカットし、
AIによるダミー操作へシームレスに切り替えます。
"""

import os
import time
import struct
import select
import threading
import logging
from typing import Callable, Optional
from core.controller_state import ControllerState, SwitchButton, SwitchHat

logger = logging.getLogger("Passthrough")

# Linux Joystick API イベント定数
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS   = 0x02
JS_EVENT_INIT   = 0x80

# Switch Pro Controller の js0 ボタンマッピング (標準 Linux ドライバ)
BTN_MAP = {
    0: SwitchButton.B,
    1: SwitchButton.A,
    2: SwitchButton.X,
    3: SwitchButton.Y,
    4: SwitchButton.CAPTURE,
    5: SwitchButton.L,
    6: SwitchButton.R,
    7: SwitchButton.ZL,
    8: SwitchButton.ZR,
    9: SwitchButton.MINUS,
    10: SwitchButton.PLUS,
    11: SwitchButton.HOME,
    12: SwitchButton.LCLICK,
    13: SwitchButton.RCLICK,
}


class ControllerPassthrough:
    def __init__(self, driver, js_device_path: str = "/dev/input/js0"):
        self.driver = driver
        self.js_device_path = js_device_path
        self.state = ControllerState()
        
        self.is_running = False
        self.is_connected = False
        self.bot_active = False  # True の時はプロコンを無視してBOTが操作
        # 実機プロコンがUSB(有線)かBluetoothか。 "usb" / "bluetooth" / "unknown"
        self.link_type = "unknown"

        self.hat_x = 0
        self.hat_y = 0

        self.thread: Optional[threading.Thread] = None
        self._fd: Optional[int] = None

    def _detect_link_type(self) -> str:
        """/sys/class/input/jsX/device のシンボリックリンク先のパスから、
        実機プロコンがUSB接続かBluetooth接続かを判定する。
        """
        name = os.path.basename(self.js_device_path)  # 例: "js0"
        sys_path = f"/sys/class/input/{name}/device"
        try:
            real_path = os.path.realpath(sys_path).lower()
        except OSError:
            return "unknown"

        if "bluetooth" in real_path:
            return "bluetooth"
        if "usb" in real_path:
            return "usb"
        return "unknown"

    def start(self):
        """パススルー監視スレッドを開始"""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None

    def set_bot_active(self, active: bool):
        """BOT稼働フラグの切り替え"""
        self.bot_active = active
        if active:
            logger.info("[Passthrough] BOTが有効化されました。プロコン入力をバイパスします。")
        else:
            logger.info("[Passthrough] BOTが停止しました。プロコン入力をSwitchへ中継再開します。")

    def _update_hat(self):
        """十字キー (HatX, HatY) の状態を SwitchHat に変換"""
        if self.hat_x == 0 and self.hat_y < 0:
            self.state.hat = SwitchHat.TOP
        elif self.hat_x > 0 and self.hat_y < 0:
            self.state.hat = SwitchHat.TOP_RIGHT
        elif self.hat_x > 0 and self.hat_y == 0:
            self.state.hat = SwitchHat.RIGHT
        elif self.hat_x > 0 and self.hat_y > 0:
            self.state.hat = SwitchHat.BOTTOM_RIGHT
        elif self.hat_x == 0 and self.hat_y > 0:
            self.state.hat = SwitchHat.BOTTOM
        elif self.hat_x < 0 and self.hat_y > 0:
            self.state.hat = SwitchHat.BOTTOM_LEFT
        elif self.hat_x < 0 and self.hat_y == 0:
            self.state.hat = SwitchHat.LEFT
        elif self.hat_x < 0 and self.hat_y < 0:
            self.state.hat = SwitchHat.TOP_LEFT
        else:
            self.state.hat = SwitchHat.CENTER

    def _loop(self):
        """プロコンからのイベントを読み込み、即座にSwitchへ転送するメインループ"""
        logger.info(f"[*] プロコン中継エンジン待機中 ({self.js_device_path})...")

        while self.is_running:
            # デバイスの接続チェック
            if not os.path.exists(self.js_device_path):
                if self.is_connected:
                    logger.warning("[!] プロコンが切断されました。再接続を待機します。")
                    self.is_connected = False
                    self.link_type = "unknown"
                time.sleep(1.0)
                continue

            try:
                self._fd = os.open(self.js_device_path, os.O_RDONLY | os.O_NONBLOCK)
                self.is_connected = True
                self.link_type = self._detect_link_type()
                logger.info(f"[+] プロコンが正常に接続されました！({self.link_type}) 中継を開始します。")

                while self.is_running and os.path.exists(self.js_device_path):
                    # select でイベント到着を待つ (タイムアウト 0.1秒)
                    r, _, _ = select.select([self._fd], [], [], 0.1)
                    if not r:
                        continue

                    # スティックを速く動かすと短時間に多数の軸イベントが
                    # 発生する。1イベントごとに送信すると、送信(IPC)の方が
                    # イベント発生より遅くなった場合に古い状態の送信が
                    # 後からキューに積まれ、実質的な反応が遅れる。
                    # なので読める分を全部読み切り、最新の状態を1回だけ送る。
                    got_event = False
                    while True:
                        try:
                            chunk = os.read(self._fd, 8)
                        except BlockingIOError:
                            break
                        if len(chunk) < 8:
                            break
                        got_event = True

                        _, value, event_type, number = struct.unpack("IhBB", chunk)
                        event_type &= ~JS_EVENT_INIT  # 初期化フラグを除去

                        if event_type == JS_EVENT_BUTTON:
                            btn = BTN_MAP.get(number)
                            if btn:
                                self.state.set_button(btn, bool(value))

                        elif event_type == JS_EVENT_AXIS:
                            # -32767 〜 +32767 を -100.0 〜 +100.0 に変換
                            norm_val = max(-100.0, min(100.0, (value / 32767.0) * 100.0))

                            if number == 0:    # Lスティック X
                                self.state.lx = norm_val
                            elif number == 1:  # Lスティック Y (倒すと負値になるため反転)
                                self.state.ly = -norm_val
                            elif number == 2:  # Rスティック X
                                self.state.rx = norm_val
                            elif number == 3:  # Rスティック Y
                                self.state.ry = -norm_val
                            elif number == 4:  # 十字キー 左右
                                self.hat_x = value
                                self._update_hat()
                            elif number == 5:  # 十字キー 上下
                                self.hat_y = value
                                self._update_hat()

                    # BOTが動いていない時は、プロコンの操作をそのままSwitchへパススルー！
                    if got_event and not self.bot_active:
                        self.driver.send_state(self.state)

            except Exception as e:
                logger.error(f"プロコン読み出しエラー: {e}")
                time.sleep(1.0)
            finally:
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except Exception:
                        pass
                    self._fd = None
