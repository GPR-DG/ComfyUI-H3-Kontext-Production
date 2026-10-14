"""FREE loopback mock: returns a known blue PNG, not semantic background repair."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from mock_api import MockAPI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--duration", type=float, default=0, help="Exit after N seconds; default waits for Ctrl+C")
    parser.add_argument("--primary-status", type=int, default=401, help="401 demonstrates safe fallback; 500 is uncertain")
    parser.add_argument("--async", dest="async_task", action="store_true", help="Backup returns a completed async task")
    args = parser.parse_args()
    api = MockAPI(args.port)
    api.set_plan("p0", status=args.primary_status)
    for pid in ("p1", "p2", "p3"):
        if args.async_task:
            api.set_plan(pid, **{"async": True, "task_status": "succeeded"})
    print("FREE loopback mock API " + api.base_url + " (known blue PNG; no semantic repair)", flush=True)
    print(json.dumps({
        "base_urls": {pid: api.url(pid) for pid in ("p0", "p1", "p2", "p3")},
        "primary_status": args.primary_status, "key_env": "H3_MOCK_KEY",
        "model_ids": ["model-p0", "model-p1", "model-p2", "model-p3"],
        "edit_path": "/images/edits", "discovery_path": "/models", "poll_path": "/tasks/{task_id}",
    }, indent=2), flush=True)
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        api.close()


if __name__ == "__main__":
    main()
