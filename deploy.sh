#!/bin/bash
# ==============================================================================
# このリポジトリをラズパイへ転送し、サービスを再起動するだけのヘルパースクリプト
# 使い方: ./deploy.sh [user@host]  (省略時は joho@raspberrypi.local)
# ==============================================================================

set -e

PI_HOST="${1:-joho@raspberrypi.local}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_DIR="pseude-splatoon-controller"

echo "=========================================================="
echo "  Deploy -> $PI_HOST:~/$REMOTE_DIR"
echo "=========================================================="

if command -v rsync >/dev/null 2>&1; then
    rsync -av --delete \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.DS_Store' \
        --exclude 'venv' \
        "$APP_DIR/" "$PI_HOST:~/$REMOTE_DIR/"
else
    echo "[*] rsyncが無いのでscpで全転送します (venv等の除外はできません)"
    ssh "$PI_HOST" "mkdir -p ~/$REMOTE_DIR"
    scp -r "$APP_DIR"/core "$APP_DIR"/web "$APP_DIR"/nxbt_patches \
        "$APP_DIR"/setup.sh "$APP_DIR"/run_local_preview.py "$APP_DIR"/README.md \
        "$PI_HOST:~/$REMOTE_DIR/"
fi

echo "[*] サービスを再起動します..."
ssh -t "$PI_HOST" "sudo systemctl restart splatoon-controller.service && sudo systemctl status splatoon-controller.service --no-pager -l | head -n 15"

echo ""
echo "[OK] デプロイ完了。"
