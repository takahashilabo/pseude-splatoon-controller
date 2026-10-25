"""
NXBT (Bluetooth Pro Controller Emulation) Driver
BlueZ経由でSwitchへ直接「プロコン」としてBluetoothペアリングし、
リアルタイムに入力を送信する。SwitchHIDDriverと同じインターフェース(send_state/reset/close)を
持つため、core.passthrough.ControllerPassthroughやweb/app.pyから透過的に差し替えられる。
"""

import logging
import threading
import time
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
        # コントローラのstate proxyを1回だけ取得してキャッシュする。
        # 毎回 self._nx.manager_state[index] を経由すると、外側Manager
        # ->内側Managerの2段IPCになり、呼び出し頻度(特にIMUの120Hz)に
        # 比例して遅延が乗る。proxyオブジェクト自体はコントローラ生存中
        # 不変なので、キャッシュして1段分のIPCを毎回削る。
        self._state = None
        # 入力送信を一時停止するフラグ (Bluetooth接続自体はそのまま維持する)
        self._output_muted = False

        # --- 一時的な計測用 (レイテンシ調査のため) ---
        # ラベルごとに直近の書き込み時間を集計し、一定間隔でまとめてログ出力する。
        self._timing_samples = {}   # label -> [elapsed_ms, ...]
        self._timing_last_log = {}  # label -> last logged wall time
        self._timing_log_interval = 2.0

        if self.is_mock:
            logger.info("[*] nxbt パッケージが見つからないため [Mockモード (シミュレーション)] で動作します。")
            return

        try:
            self._nx = nxbt.Nxbt()
            self._create_and_connect()
        except Exception as e:
            logger.warning(f"[!] nxbt の初期化に失敗 ({e})。Mockモードに移行します。")
            self.is_mock = True

    def _create_and_connect(self):
        """コントローラを生成し、Switchへの接続待ちを開始する。"""
        self._controller_index = self._nx.create_controller(
            nxbt.PRO_CONTROLLER,
            reconnect_address=self._nx.get_switch_addresses(),
        )
        self._state = self._nx.manager_state[self._controller_index]
        threading.Thread(target=self._wait_connection, daemon=True).start()

    def disconnect(self):
        """入力送信を一時停止する (Bluetooth接続自体は維持したまま)。

        以前は remove_controller()/create_controller() でコントローラ自体を
        作り直す実装だったが、古いコントローラのプロセスがBluetoothアダプタを
        解放する前に新しいコントローラがそれを使おうとして競合し、接続不能に
        なる既知の不安定要因があった(過去にも同種の再接続処理で実際に発生した
        regressionと同じパターン)。本物のプロコンと直接比較したいだけであれば
        Bluetooth接続自体を切る必要はなく、送信を止めるだけで十分なので、
        よりリスクの低いこちらに変更した。
        """
        # 停止直前の入力(スティックを倒した状態など)が残り続けないよう、
        # 停止前にニュートラル状態を一度送っておく。
        if self._state is not None:
            try:
                self._state["direct_input"] = self._nx.create_input_packet()
            except Exception:
                pass
        self._output_muted = True
        logger.info("[*] Switchへの入力送信を一時停止しました (接続は維持)。")

    def reconnect(self):
        """一時停止していた入力送信を再開する。"""
        self._output_muted = False
        logger.info("[*] Switchへの入力送信を再開しました。")

    def _record_timing(self, label: str, elapsed_ms: float):
        """IPC書き込み1回あたりの時間を集計し、2秒おきに平均/最大/回数をログ出力する。
        レイテンシ調査用の一時的な計測なので、原因が特定できたら削除してよい。
        """
        samples = self._timing_samples.setdefault(label, [])
        samples.append(elapsed_ms)

        now = time.time()
        last = self._timing_last_log.get(label, 0.0)
        if now - last >= self._timing_log_interval:
            if samples:
                avg = sum(samples) / len(samples)
                mx = max(samples)
                logger.info(
                    f"[timing] {label}: avg={avg:.2f}ms max={mx:.2f}ms "
                    f"count={len(samples)} (直近{self._timing_log_interval:.0f}秒)")
            self._timing_samples[label] = []
            self._timing_last_log[label] = now

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
        if self.is_mock or self._state is None or not self.is_connected or self._output_muted:
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
            t0 = time.perf_counter()
            self._state["direct_input"] = packet
            self._record_timing("direct_input", (time.perf_counter() - t0) * 1000)
        except Exception as e:
            logger.error(f"NXBT入力送信エラー: {e}")

    def send_imu(self, accel_xyz, gyro_xyz):
        """
        IMU(ジャイロ/加速度)の生データをnxbtへ渡す。
        accel_xyz/gyro_xyzはSwitch側の生単位(1/4096g, 1/14247dps)の整数3要素。
        nxbt_patches/protocol.py の set_imu_samples() 拡張が適用されている
        場合のみ有効 (未適用のnxbtでは何も起きない)。
        """
        if self.is_mock or self._state is None or self._output_muted:
            return
        try:
            imu_samples = list(accel_xyz) + list(gyro_xyz)
            t0 = time.perf_counter()
            self._state["direct_imu"] = imu_samples
            self._record_timing("direct_imu", (time.perf_counter() - t0) * 1000)
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
