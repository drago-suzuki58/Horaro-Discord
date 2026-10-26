# Horaro-Discord 開発メモ

## 構成

- Python パッケージは `src/horaro_discord/`。uv で管理し、`uv run horaro-discord` で起動する。
- `schedule.py` が共通の `Schedule`・`Item` と保存形式を定義する。Horaro はそのまま、RiJ は取得時にこの形式へ変換する。通知・表示処理に取得元ごとの条件を追加しない。
- `timeline.py` は Discord と HTTP に依存しない純粋関数だけを置く。現在時刻は引数で受け取る。
- `scheduler.py` は Discord への送信・編集を `DiscordPort` 経由で行う。実装は `bot.py` の `DiscordAdapter`。
- 表示言語は日本語のみ。コマンド名は英語、説明と応答は日本語。

## 通知の仕様

- 通知を事前に予約しない。定期ループ（30 秒）が、その時点で最新のスケジュールから送信・編集すべき通知を `timeline.plan` で毎回計算する。旧実装は予約済みの通知がスケジュール変更に追従せず、古い時刻で通知していた。
- 送信直前に、取得から `LIVE_FETCH_INTERVAL` 以上経っていれば再取得してから計算し直す。
- Horaro の行には ID がない。プログラムはキー列の値と出現回数で識別する（`timeline.item_keys`）。キー列を変えるときは `rekey` で記録を移す。
- 通知済みのプログラムの開始予定が変わったらメッセージを編集し、`RENOTIFY_SHIFT`（5 分）以上ずれたら再通知する。削除されたら編集で示す。開始済みで未通知のプログラムは送らない。
- 登録・変更・削除の DB 操作は必ずギルドで絞る。

## Horaro API

- 取得先は horaro.net の `/-/api/v1`。horaro.org は静的アーカイブで API は 410 を返す。horaro.org の URL は horaro.net に読み替える（ID と slug は同じ）。
- スケジュールは `/-/api/v1/schedules/{id}` を `If-Modified-Since` 付きで取得する（変更なしなら 304）。
- ticker API は時刻がすべて同じ値になる不具合があるため使わない。現在・次は全件の `scheduled_t` から計算する。
- 一覧のページサイズは `max`（ドキュメントの `size` は効かない）。エラーは HTML で返る。
- 非公開の列が見えない場合、`columns` と `data` から列ごと消える。列は位置ではなく名前で扱う。

## RTA in Japan 公式

- `rij.py` が `https://rtain.jp/schedule/data/` の公開 JSON（`schemaVersion: 2`）を取得する。Horaro 互換 API ではない。
- 登録 URL は `https://rtain.jp/schedule/?event={id}`。スケジュールは `{id}.json`、検索は `events.json` を使う。公式ページと同様にクエリでキャッシュを回避する。
- 開始時刻は `event.startsAt` から `estimateSeconds + setupSeconds` を累積して計算する。各プログラムの長さは `estimateSeconds` のみ。最後の準備時間はスケジュール終了に含めない。
- `run.id` の永続性は前提にせず、Horaro と同じキー列による識別を使う。
- DB の `source` で再取得先を選ぶ。RiJ の保存 ID は `rij:{event_id}` とし、既存の Horaro ID・登録・通知履歴を変更しない。スキーマ v1 から v2 への移行は `source` 列の追加のみ。
- 対応先は固定し、登録 URL から任意のホストやパスを取得しない。

## 確認

```sh
uv run pytest
uv run ruff check && uv run ruff format --check
uv run mypy
```

スケジュール変更への追従は `tests/test_scheduler.py`（偽の時計・Horaro/RiJ・Discord で両形式のイベントを再現）と `tests/test_timeline.py` で確認する。DB 移行は `tests/test_store.py` で旧スキーマの登録・通知履歴が保持されることを確認する。Discord との実際の通信はテスト用サーバーで手動確認する。
