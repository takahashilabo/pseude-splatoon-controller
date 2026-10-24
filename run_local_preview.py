#!/usr/bin/env python3
"""
Local Preview Runner for Mac / PC
---------------------------------
Mac上でスマホ画面 (Web UI) とボットAIの動作をテストするためのスクリプトです。
実行すると自動でローカルサーバーが立ち上がり、ブラウザから動作を確認できます。
"""

import os
import sys
import webbrowser

# パス追加
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from web.app import app

if __name__ == "__main__":
    port = 5050
    url = f"http://127.0.0.1:{port}"
    print("=" * 65)
    print("  Splatoon Dummy Bot Controller - Local Preview")
    print(f"  ブラウザで以下のURLを開いて動作確認できます:")
    print(f"  👉  {url}")
    print("=" * 65)
    
    # 自動でブラウザを開く
    try:
        webbrowser.open(url)
    except Exception:
        pass

    app.run(host="0.0.0.0", port=port, debug=False)
