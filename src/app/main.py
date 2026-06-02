"""Cloud Run job / local batch エントリポイント。引数でコマンドを分岐する。

python -m app.main seed-csv           # feature_emb_{a,b}.csv を生成
python -m app.main load-bq            # CSV を BigQuery へロード
python -m app.main register-fs        # BQ View + Feature Group / Feature を登録
python -m app.main batch-read-offline # BigQuery から特徴量取得 → stdout + GCS JSONL

注意:
- Feature View は作成しない
- Online Store は作成しない
- Feature View sync は実行しない
- Redis は触らない
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from app.batch import read_offline
from app.data import load_bq, seed_csv
from app.feature_store import register

COMMANDS: dict[str, Callable[[], None]] = {
    "seed-csv": seed_csv.run,
    "load-bq": load_bq.run,
    "register-fs": register.run,
    "batch-read-offline": read_offline.run,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: python -m app.main <{'|'.join(COMMANDS)}>", file=sys.stderr)
        return 2

    command = argv[1]
    handler = COMMANDS.get(command)

    if handler is None:
        print(
            f"[error] unknown command: {command} (expected {'|'.join(COMMANDS)})",
            file=sys.stderr,
        )
        return 2

    handler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
