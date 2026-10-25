"""
Splatoon Dummy Controller - Mobile Web Server & API
スマホのブラウザからワンタップでSwitchのダミー自動操作を開始/停止できるWebアプリケーション
"""

import sys
import os
import time
import subprocess
import threading
import logging
from flask import Flask, render_template, jsonify, request

# パス追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.human_splatoon_ai import HumanSplatoonAI, PlayStyle
from core.nxbt_driver import NXBTDriver
from core.passthrough import ControllerPassthrough
from core.imu_passthrough import IMUPassthrough

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WebApp")

app = Flask(__name__)


class BotWorker:
    def __init__(self):
        self.driver = NXBTDriver()
        self.ai = HumanSplatoonAI()
        self.passthrough = ControllerPassthrough(self.driver)
        self.passthrough.start()  # プロコン中継を常時監視
        self.imu_passthrough = IMUPassthrough(self.driver)
        self.imu_passthrough.start()  # プロコンのジャイロ/加速度を常時中継
        
        self.is_running = False
        self.lock = threading.Lock()
        self.thread: threading.Thread = None
        self.start_time = 0.0
        self.auto_stop_sec = 300  # デフォルト5分で自動停止 (スプラ1試合分)

    def start(self, style_name: str = "balanced", auto_stop_sec: int = 300):
        with self.lock:
            if self.is_running:
                return
            try:
                style = PlayStyle(style_name)
            except ValueError:
                style = PlayStyle.BALANCED
            
            self.ai.set_style(style)
            self.auto_stop_sec = auto_stop_sec
            self.start_time = time.time()
            self.is_running = True
            
            # プロコンの入力をバイパスしてBOT操作へ
            self.passthrough.set_bot_active(True)
            self.imu_passthrough.set_bot_active(True)

            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            logger.info(f"ダミー操作を開始しました (スタイル: {style_name}, 制限時間: {auto_stop_sec}秒)")

    def stop(self):
        with self.lock:
            if not self.is_running:
                return
            self.is_running = False
            # プロコン中継へ復帰
            self.passthrough.set_bot_active(False)
            self.imu_passthrough.set_bot_active(False)

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.driver.reset()
        logger.info("ダミー操作を停止し、プロコン中継へ復帰しました。")

    def _run_loop(self):
        last_time = time.time()
        while self.is_running:
            now = time.time()
            dt = now - last_time
            last_time = now

            # 自動停止判定
            elapsed = now - self.start_time
            if self.auto_stop_sec > 0 and elapsed >= self.auto_stop_sec:
                logger.info("制限時間に達したため自動停止しました。")
                self.is_running = False
                break

            state = self.ai.update(dt)
            self.driver.send_state(state)
            time.sleep(0.04)  # ~25Hz更新

        self.driver.reset()

    def disconnect_switch(self):
        """Switchへの入力送信を一時停止する (本物のプロコンを直接Switchに繋いで比較したい時などに使う)"""
        self.driver.disconnect()

    def reconnect_switch(self):
        """一時停止していたSwitchへの入力送信を再開する"""
        self.driver.reconnect()

    def get_status(self):
        status = self.ai.get_status_dict()
        status["is_running"] = self.is_running
        status["is_mock"] = self.driver.is_mock
        status["switch_paired"] = self.driver.is_connected
        status["switch_output_muted"] = self.driver._output_muted
        status["controller_connected"] = self.passthrough.is_connected
        status["controller_link_type"] = self.passthrough.link_type
        status["elapsed_sec"] = round(time.time() - self.start_time, 1) if self.is_running else 0.0
        status["auto_stop_sec"] = self.auto_stop_sec
        return status


worker = BotWorker()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(worker.get_status())


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    style = data.get("style", "balanced")
    auto_stop = int(data.get("auto_stop_sec", 300))
    worker.start(style, auto_stop)
    return jsonify({"success": True, "status": worker.get_status()})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    worker.stop()
    return jsonify({"success": True, "status": worker.get_status()})


@app.route("/api/switch/disconnect", methods=["POST"])
def api_switch_disconnect():
    worker.disconnect_switch()
    return jsonify({"success": True, "status": worker.get_status()})


@app.route("/api/switch/reconnect", methods=["POST"])
def api_switch_reconnect():
    worker.reconnect_switch()
    return jsonify({"success": True, "status": worker.get_status()})


@app.route("/api/system/shutdown", methods=["POST"])
def api_system_shutdown():
    logger.info("[*] Webからシャットダウン要求を受け付けました。")
    # レスポンスを返した後にシャットダウンが始まるよう、少し遅延させてバックグラウンドで実行
    subprocess.Popen(["shutdown", "-h", "+0"])
    return jsonify({"success": True})


if __name__ == "__main__":
    # ラズパイおよび同一Wi-Fi内のスマホからアクセスできるよう 0.0.0.0 で起動
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
