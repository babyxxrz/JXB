# settings.py — 服务端内部设置(与看板 /api/config 分离)
# /api/config 是看板维护的公开配置(契约 8.2);control_url 等联调设置属于
# 服务部署侧,单独存放,避免被看板保存配置时覆盖。

import json
import os

from .db import DATA_DIR

SETTINGS_PATH = DATA_DIR / "server.json"

DEFAULTS = {
    # 控制模块下行桥地址(朱玉贺 dofbot_event_bridge 的下行端点),环境变量优先
    "control_url": "http://127.0.0.1:9100",
    # 指令/轮询超时(秒),超过视为不可达或 CONTROL_TIMEOUT
    "control_timeout_s": 5.0,
}


def load_settings() -> dict:
    """读取服务端设置,缺失项用默认值补齐。"""
    base = dict(DEFAULTS)
    base["control_url"] = os.environ.get("JXB_CONTROL_URL", base["control_url"])
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        base.update({k: v for k, v in saved.items() if k in DEFAULTS})
        return base
    except FileNotFoundError:
        save_settings(base)
        return base


def save_settings(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
