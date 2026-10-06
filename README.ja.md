# Horaro Discord Bot

[Horaro](https://horaro.net) のスケジュールを Discord サーバーに登録し、各プログラムの開始前にチャンネルへ通知する Bot です。

[English](README.md)

## できること

- 登録したスケジュールの各プログラムを、開始の指定分前にチャンネルへ通知します。
- 主催者がスケジュールを変更した場合も、最新のスケジュールに合わせて通知します。
  - イベント中は 1 分ごとに Horaro を確認します。
  - 通知済みのプログラムの開始予定が変わると、通知メッセージを編集して変更前後の時刻を示します。5 分以上ずれた場合は、新しい時刻に合わせてもう一度通知します。
  - スケジュールから削除されたプログラムは、通知メッセージにその旨を表示します。
- 現在・次のプログラムや今後のプログラムを Discord から確認できます。
- スケジュールに合わせた Discord のサーバーイベントを作成し、開始・終了時刻を自動で更新できます。

時刻は Discord のタイムスタンプで表示されるため、見る人のタイムゾーンで表示されます。表示言語は日本語です。

## コマンド

`/horaro` は誰でも使えます。`/horaro-admin` は既定で「サーバーの管理」権限を持つメンバーだけが使えます（サーバー設定の「連携サービス」から変更できます）。

| コマンド | 内容 |
|---|---|
| `/horaro list` | 登録されているスケジュールの一覧 |
| `/horaro now [schedule]` | 現在と次のプログラム |
| `/horaro upcoming schedule [count]` | 今後のプログラム（最大 10 件） |
| `/horaro-admin add url [channel] [notice] [server_event]` | スケジュールを登録します |
| `/horaro-admin edit schedule [channel] [notice] [key_column] [server_event]` | 登録内容を変更します |
| `/horaro-admin remove schedule` | 登録を解除します |
| `/horaro-admin refresh [schedule]` | Horaro から最新のスケジュールをすぐに取得します |

- `url` にはスケジュールの URL（例: `https://horaro.net/event/schedule`）を指定します。
  - イベントの URL を指定すると、スケジュールを選択メニューから選べます。
  - イベント名を入力すると、Horaro の検索結果が候補に出ます。
  - horaro.org の URL も使えます（horaro.net として扱います）。
- `notice` は開始の何分前に通知するかです（既定 10 分）。
- `key_column` は通知の見出しにする列です。プログラムの識別にも使うため、ゲーム名など変わりにくい列を選んでください。登録時はゲーム名らしい列を自動で選びます。
- `server_event` を有効にすると、Discord のサーバーイベントを作成します。すでに開始しているスケジュールには作成できません。

## 導入方法

[uv](https://docs.astral.sh/uv/) が必要です。

1. リポジトリを取得して依存関係をインストールします。

   ```sh
   git clone https://github.com/drago-suzuki58/Horaro-Discord.git
   cd Horaro-Discord
   uv sync --no-dev
   ```

2. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーションと Bot を作成し、トークンを取得します。特権インテントは不要です。

3. 次の URL の `CLIENT_ID` をアプリケーション ID に置き換えて開き、Bot をサーバーに招待します。

   ```
   https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot+applications.commands&permissions=17867063954432
   ```

   付与される権限は「チャンネルを見る」「メッセージを送信」「スレッドでメッセージを送信」「イベントの作成」です。

4. `.env.example` を `.env` にコピーし、`DISCORD_TOKEN` を設定します。

5. 起動します。

   ```sh
   uv run horaro-discord
   ```

登録内容と通知の記録は `DATABASE_PATH`（既定 `data/horaro-discord.db`）に保存されます。

## 注意

- 通知は Horaro 上の予定時刻に基づきます。実際の進行が遅れていても、主催者が Horaro のスケジュールを更新するまでは反映されません。
- 非公開のスケジュールと、非公開の列（hidden column）には対応していません。
- Bot が停止していた間に開始したプログラムは、起動後に通知しません。
- horaro.org は 2026 年に静的アーカイブとなったため、データは後継の horaro.net の API から取得します。

## 開発

```sh
uv sync
uv run pytest
uv run ruff check
uv run mypy
```
