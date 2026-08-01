"""待受ソケットの確定（bind と確定ポートの書き戻し / 公開）。"""
from __future__ import annotations

import logging
import socket
from pathlib import Path

from ai_monitor.shared.settings import Settings

logger = logging.getLogger(__name__)

# 待受アドレス（外部公開しない）
LISTEN_HOST = "127.0.0.1"


def bind_listen_socket(settings: Settings, port_path: Path) -> socket.socket:
    """待受ソケットを bind し、確定したポートを設定へ書き戻してファイルへ公開する。"""
    # SO_REUSEADDR は設定しない（使用中ポートの指定を検出できなくなるため）
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    requested = settings.port
    try:
        sock.bind((LISTEN_HOST, requested))
    except OSError:
        # 設定も公開ファイルも変更せず、そのまま呼び出し元へ伝播する
        sock.close()
        logger.error("待受ポートを確保できませんでした: requested=%s", requested)
        raise
    # 確定したポートを設定へ書き戻す（MCP 接続先とフックの送信先はここから組み立てられる）
    resolved = sock.getsockname()[1]
    settings.port = resolved
    # 監視役と外部ツールの参照先として確定値を公開する
    port_path.parent.mkdir(parents=True, exist_ok=True)
    port_path.write_text(str(resolved), encoding="utf-8")
    logger.info("待受ポートを確定しました: port=%s port_path=%s", resolved, port_path)
    return sock
