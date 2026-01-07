#!/usr/bin/env python3
"""Kiro API Proxy 启动脚本"""
import sys

if __name__ == "__main__":
    # 如果有子命令参数，使用 CLI 模式
    if len(sys.argv) > 1 and sys.argv[1] in ("accounts", "login", "status", "serve"):
        from kiro_proxy.cli import main
        main()
    else:
        # 兼容旧的启动方式: python run.py [port]
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
        from kiro_proxy.main import run
        run(port)
