#!/bin/bash
# ==============================================================================
# Raspberry Pi 4 - Splatoon Dummy Controller Auto-Setup Script
# (Bluetooth Pro Controller Emulation via NXBT — USBケーブル不要)
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "[!] このスクリプトは sudo で実行してください。"
  echo "    例: sudo ./setup.sh"
  exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=========================================================="
echo "  Raspberry Pi Splatoon Dummy Controller Installer"
echo "  Target Directory: $APP_DIR"
echo "=========================================================="

# 1. 依存パッケージのインストール (Bluetooth, Python, dbus)
#    dbus-pythonはpipでソースビルドすると新しいPython(3.12+)で`imp`モジュール
#    廃止のため失敗するので、apt版のビルド済みパッケージを使う。
echo "[1/4] 必要なパッケージをインストール中..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv python3-dbus bluetooth bluez \
    libdbus-glib-1-dev libdbus-1-dev

# 2. venv作成 (--system-site-packagesでapt版python3-dbusを継承しつつnxbt/flaskを導入)
echo "[2/4] Python仮想環境を作成中 (venv/)..."
python3 -m venv --system-site-packages "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
# nxbtのsetup.pyは2021年当時の古いバージョンにdbus-python等を厳密固定しており、
# それをそのままインストールすると新しいPython(3.12+)でビルドが失敗する。
# 実際にnxbtのNxbtクラス(今回利用する部分)が実行時に必要とするのは標準ライブラリと
# dbus(=apt版python3-dbusで用意済み)のみなので、--no-depsで依存解決をスキップする。
"$APP_DIR/venv/bin/pip" install --no-deps nxbt
"$APP_DIR/venv/bin/pip" install flask evdev

# nxbt本体にジャイロ/加速度の実データを流せるようにする独自パッチを適用
# (nxbt_patches/ 以下のファイルで、pipが入れたnxbtの該当ファイルを上書きする)
NXBT_PKG_DIR=$(find "$APP_DIR/venv/lib" -maxdepth 4 -type d -name nxbt | head -n 1)
if [ -n "$NXBT_PKG_DIR" ] && [ -d "$NXBT_PKG_DIR" ]; then
    cp "$APP_DIR/nxbt_patches/protocol.py" "$NXBT_PKG_DIR/controller/protocol.py"
    cp "$APP_DIR/nxbt_patches/server.py" "$NXBT_PKG_DIR/controller/server.py"
    cp "$APP_DIR/nxbt_patches/nxbt.py" "$NXBT_PKG_DIR/nxbt.py"
    echo "  -> nxbtにジャイロ中継用パッチを適用しました。"
else
    echo "  [!] nxbtのインストール先が見つからず、パッチを適用できませんでした: $NXBT_PKG_DIR"
fi

# 3. Bluetooth Input プラグインの無効化 (NXBTが入力を直接ハンドリングするため必須)
echo "[3/4] Bluetooth 設定を調整中..."
BT_MAIN_CONF="/etc/bluetooth/main.conf"
if [ -f "$BT_MAIN_CONF" ] && ! grep -q "^DisablePlugins=input" "$BT_MAIN_CONF"; then
    echo "DisablePlugins=input" >> "$BT_MAIN_CONF"
    echo "  -> $BT_MAIN_CONF に 'DisablePlugins=input' を追加しました。"
fi
systemctl enable bluetooth
systemctl restart bluetooth

# 4. Webコントローラー 自動起動サービスの作成
echo "[4/4] Webコントローラー 自動起動サービスを作成中..."
cat << 'EOF' > /etc/systemd/system/splatoon-controller.service
[Unit]
Description=Splatoon Dummy Controller Web Server
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
Type=simple
User=root
WorkingDirectory=APP_DIR_PLACEHOLDER
Environment="PORT=80"
ExecStart=APP_DIR_PLACEHOLDER/venv/bin/python3 APP_DIR_PLACEHOLDER/web/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sed -i "s|APP_DIR_PLACEHOLDER|$APP_DIR|g" /etc/systemd/system/splatoon-controller.service

# サービスの有効化
systemctl daemon-reload
systemctl enable splatoon-controller.service

echo ""
echo "=========================================================="
echo "  [OK] セットアップが完了しました！"
echo "=========================================================="
echo "  設定を反映するため、Raspberry Pi を再起動してください:"
echo "    sudo reboot"
echo ""
echo "  再起動後、Switch側で「コントローラー」→「持ち方/順番を変える」"
echo "  画面を開いた状態で、ラズパイと同じWi-Fiに繋いだスマホのブラウザで"
echo "  http://raspberrypi.local (またはラズパイのIPアドレス) を開くと"
echo "  操作画面が表示されます。初回のみ、画面上で自動的にSwitchとの"
echo "  Bluetoothペアリングが行われます。"
echo "=========================================================="
