import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from app import collector, db, service  # noqa: E402
from app.config import load_config  # noqa: E402
from app.steam import SteamClient  # noqa: E402
from app.web import create_app  # noqa: E402

log = logging.getLogger("run")

STARTER_APPS = [
    730, 570, 578080, 1172470, 1086940, 1245620, 1091500, 292030, 3240220, 1174180,
    2358720, 553850, 1623730, 252490, 413150, 105600, 892970, 1145360, 1158310,
    381210, 367520, 1593500, 1426210, 1817070, 1938090, 2195250, 582010, 1446780,
    814380, 377160, 489830, 289070, 427520, 294100, 945360, 242760, 1326470,
    1888930, 2050650, 1196590, 883710, 251570, 322330, 108600, 264710, 394360,
    236850, 281990, 1172620, 582660, 1203220, 1966720, 230410, 238960
]


def background(cfg):
    steam = SteamClient(cfg)
    first = True
    while True:
        try:
            log.info("collector cycle: %s", collector.run_cycle(cfg, steam))
            if first:
                conn = db.connect(cfg.db_path)
                for aid in STARTER_APPS:
                    try:
                        service.ensure_game(conn, steam, cfg, aid)
                    except Exception as e:
                        log.warning("starter %s failed: %s", aid, e)
                conn.close()
                first = False
        except Exception:
            log.exception("collector cycle failed (will retry)")
        time.sleep(cfg.collector_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    app = create_app(cfg)
    if os.getenv("AUTO_COLLECT", "1") != "0":
        threading.Thread(target=background, args=(cfg,), daemon=True).start()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"\n  SteamTracker running ->  http://localhost:{port}\n  (prices and catalog update automatically)\n")
    app.run(host=host, port=port, threaded=True, debug=False)

