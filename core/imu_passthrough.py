"""
Nintendo Switch Controller IMU (ジャイロ/加速度) パススルー
-------------------------------------------------------
本物のプロコンのIMUを evdev (/dev/input/eventX、"... Pro Controller (IMU)") から
読み取り、NXBTDriver.send_imu() 経由でSwitchへ継続的に中継する。

座標・スケールは実機のevtestで確認済みの値を使用:
  - 加速度 (ABS_X/Y/Z): evdevの生値がそのままSwitch側の生単位(1/4096 g)と一致
  - ジャイロ (ABS_RX/RY/RZ): evdevの生値は1000倍されているため /1000 して
    Switch側の生単位(1/14247 dps)に揃える
"""

import os
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("IMUPassthrough")

try:
    import evdev
    from evdev import ecodes
    _EVDEV_AVAILABLE = True
except ImportError:
    _EVDEV_AVAILABLE = False

_GYRO_SCALE_DIVISOR = 1000


class IMUPassthrough:
    def __init__(self, driver, device_path: str = "/dev/input/event4"):
        self.driver = driver
        self.device_path = device_path
        self.bot_active = False
        self.is_running = False
        self.is_connected = False

        self._accel = [0, 0, 0]
        self._gyro = [0, 0, 0]
        self._dev: Optional["evdev.InputDevice"] = None
        self._read_thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None

    def set_bot_active(self, active: bool):
        """BOT稼働フラグの切り替え (BOT中は実機IMUの中継を止め、ニュートラルを送る)"""
        self.bot_active = active

    def start(self):
        if self.is_running:
            return
        if not _EVDEV_AVAILABLE:
            logger.info("[*] evdevパッケージが見つからないため、IMU中継を無効化します。")
            return
        self.is_running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()

    def stop(self):
        self.is_running = False

    def _read_loop(self):
        """実機プロコンのIMUデバイスから継続的に読み取り、最新値を保持する"""
        while self.is_running:
            if not os.path.exists(self.device_path):
                self.is_connected = False
                time.sleep(1.0)
                continue

            try:
                self._dev = evdev.InputDevice(self.device_path)
                self.is_connected = True
                logger.info(f"[+] IMUデバイス ({self.device_path}) に接続しました。")

                for event in self._dev.read_loop():
                    if not self.is_running:
                        break
                    if event.type == ecodes.EV_ABS:
                        if event.code == ecodes.ABS_X:
                            self._accel[0] = event.value
                        elif event.code == ecodes.ABS_Y:
                            self._accel[1] = event.value
                        elif event.code == ecodes.ABS_Z:
                            self._accel[2] = event.value
                        elif event.code == ecodes.ABS_RX:
                            self._gyro[0] = event.value // _GYRO_SCALE_DIVISOR
                        elif event.code == ecodes.ABS_RY:
                            self._gyro[1] = event.value // _GYRO_SCALE_DIVISOR
                        elif event.code == ecodes.ABS_RZ:
                            self._gyro[2] = event.value // _GYRO_SCALE_DIVISOR

                self.is_connected = False
            except OSError as e:
                logger.warning(f"[!] IMU読み取りエラー ({e})。再接続を待機します。")
                self.is_connected = False
                time.sleep(1.0)

    def _send_loop(self):
        """~120Hzで最新のIMU値(またはニュートラル)をドライバへ送信する"""
        last_log = 0.0
        while self.is_running:
            # Switch未接続でも実機の値が読めているか確認できるよう、
            # 1秒おきにログへ出力する (動作確認用)
            now = time.time()
            if self.is_connected and now - last_log >= 1.0:
                logger.info(
                    f"[IMU debug] accel={tuple(self._accel)} gyro={tuple(self._gyro)}")
                last_log = now

            if self.is_connected and not self.bot_active:
                self.driver.send_imu(tuple(self._accel), tuple(self._gyro))
            else:
                self.driver.send_imu((0, 0, 0), (0, 0, 0))
            time.sleep(1 / 120)
