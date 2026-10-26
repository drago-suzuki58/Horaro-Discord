# Horaro Discord Bot

[Horaro](https://horaro.net) または [RTA in Japan 公式サイト](https://rtain.jp/schedule/)のスケジュールを Discord サーバーに登録し、各プログラムの開始前にチャンネルへ通知する Bot です。

[English](README.md)

## できること

- 登録したスケジュールの各プログラムを、開始の指定分前にチャンネルへ通知します。
- 主催者がスケジュールを変更した場合も、最新のスケジュールに合わせて通知します。
  - イベント中は 1 分ごとに登録先のスケジュールを確認します。
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
| `/horaro-admin refresh [schedule]` | 登録先から最新のスケジュールをすぐに取得します |

- `url` には Horaro の URL（例: `https://horaro.net/event/schedule`）または RiJ 公式の URL（例: `https://rtain.jp/schedule/?event=rtaijw2026`）を指定します。取得元は URL から自動で判別します。
  - Horaro のイベントの URL を指定すると、スケジュールを選択メニューから選べます。
  - イベント名を入力すると、RiJ 公式と Horaro の検索結果が候補に出ます。候補には取得元も表示されます。
  - horaro.org の URL も使えます（horaro.net として扱います）。
- `notice` は開始の何分前に通知するかです（既定 10 分）。
- `key_column` は通知の見出しにする列です。プログラムの識別にも使うため、ゲーム名など変わりにくい列を選んでください。登録時はゲーム名らしい列を自動で選びます。
- `server_event` を有効にすると、Discord のサーバーイベントを作成します。すでに開始しているスケジュールには作成できません。

RiJ 公式のスケジュールは、たとえば次のように登録します。コマンド名は Horaro と共通です。

```text
/horaro-admin add url:https://rtain.jp/schedule/?event=rtaijw2026
```

## 導入方法

[uv](https://docs.astral.sh/uv/) が必要です。

1. リポジトリを取得して依存関係をインストールします。

   ```sh
   git clone https://github.com/drago-suzuki58/Horaro-Discord.git
   cd Horaro-Discord
   uv sync --no-dev
   ```

2. [Discord Developer Portal](https://discord.com/developers/applications) で **New Application** からアプリケーションを作成し、次の設定を行います。

   - **General Information**: **Application ID** を控えます。招待 URL の `CLIENT_ID` に使います。
   - **Bot**: Bot トークンを取得します。必要なら **Reset Token** で発行し、後で `.env` の `DISCORD_TOKEN` に設定します。Client Secret や Public Key とは別の値です。トークンは公開・共有しないでください。
   - **Bot → Privileged Gateway Intents**: **Presence Intent**・**Server Members Intent**・**Message Content Intent** はすべて **OFF のまま**で動作します。
   - **Bot → Requires OAuth2 Code Grant**: **OFF** にします。この Bot は OAuth2 のコールバック処理を持ちません。
   - **Installation → Installation Contexts**: **Guild Install**（サーバーへのインストール）を有効にします。**User Install** は不要です。コマンドはサーバー内でのみ使えます。
   - **Installation → Default Install Settings → Guild Install**: Scopes に `bot`・`applications.commands` を選択し、Permissions には後述の必要な権限だけを選択します。**OAuth2 → URL Generator** を使う場合も同じ選択です。
   - **General Information → Interactions Endpoint URL**: 空欄にします。この Bot は Gateway 接続でコマンドを受信するため、公開 HTTP サーバーやリダイレクト URL の設定は不要です。

   他のユーザーにも招待を許可する場合だけ **Bot → Public Bot** を有効にします。自分で招待して運用するだけなら不要です。

3. 次の URL の `CLIENT_ID` を Application ID に置き換えて開き、Bot をサーバーに招待します。招待するユーザーには対象サーバーの「サーバーの管理」権限が必要です。

    ```
    https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot+applications.commands&permissions=17867063954432&integration_type=0
    ```

   この URL は「チャンネルを見る」「メッセージを送信」「スレッドでメッセージを送信」「イベントの作成」を要求します。通常のテキストチャンネルへの通知だけなら、`permissions=3072` に変更できます。

4. `.env.example` を `.env` にコピーし、`DISCORD_TOKEN` を設定します。

5. 起動します。

   ```sh
   uv run horaro-discord
   ```

登録内容と通知の記録は `DATABASE_PATH`（既定 `data/horaro-discord.db`）に保存されます。

更新前には Bot を停止し、DB のバックアップを取ってください。既存の DB は起動時に自動移行され、登録と通知履歴は維持されます。既存の Horaro 登録が RiJ 公式へ自動で切り替わることはありません。切り替える場合は新しい URL を登録し、不要な旧登録を解除してください。

### Botに付与する権限

Botの権限と、コマンドを実行するユーザーの権限は別です。**Botに「管理者」を付与する必要はありません。**

| Discord上の権限 / 英語名 | 必要な場面 | 用途 |
|---|---|---|
| チャンネルを見る / View Channels | 必須 | 通知先のチャンネルにアクセスします |
| メッセージを送信 / Send Messages | 通常のチャンネルへの通知に必須 | 開始前の通知を投稿します |
| スレッドでメッセージを送信 / Send Messages in Threads | スレッドへ通知するときだけ | スレッド内へ通知を投稿します |
| イベントの作成 / Create Events | `server_event:true` を使うときだけ | Bot自身が作成するサーバーイベントの作成・予定時刻の更新・開始前の削除を行います |

招待 URL の `permissions` は、使う機能に合わせて次の値に変更できます。

| 利用する機能 | `permissions` の値 |
|---|---|
| 通常のテキストチャンネルへの通知のみ | `3072` |
| 通常の通知とサーバーイベント連携 | `17592186047488` |
| 通常の通知・スレッドへの通知・サーバーイベント連携 | `17867063954432` |

- 「チャンネルを見る」「メッセージを送信」は、サーバーのロールだけでなく**実際の通知先チャンネルでも許可**されている必要があります。非公開チャンネルやカテゴリの権限上書きを確認してください。
- スレッドを通知先にする場合は、そのスレッド内で `/horaro-admin add` を実行し、`channel` を省略します。親チャンネルの閲覧権限とスレッド内の送信権限が必要です。非公開スレッドにはBotを追加し、ロックされている場合は解除してください。Botはスレッドを作成・管理しません。
- サーバーイベントは外部URLを開催場所にする形式です。「イベントの作成」は**サーバーのロールで許可**してください。ボイスチャンネルへの接続・発言や「イベントの管理」は不要です。操作対象はBot自身が作成したイベントだけです。
- 「メッセージ履歴を読む」「メッセージの管理」は不要です。通知の編集にはDBに保存したメッセージIDを使い、Bot自身のメッセージだけを編集します。
- 「埋め込みリンク」「ファイルを添付」も不要です。現在の通知はテキストとボタンを使った Components V2 形式で、Embedや添付ファイルを使いません。
- Botに「サーバーの管理」「ロールの管理」「チャンネルの管理」「ウェブフックの管理」を付与する必要はありません。

権限の仕様はDiscord公式の[権限一覧](https://docs.discord.com/developers/topics/permissions)と[サーバーイベントの権限要件](https://docs.discord.com/developers/resources/guild-scheduled-event#guild-scheduled-event-permissions-requirements)を参照してください。

### コマンドを使うユーザーの権限

- コマンドを実行するチャンネルで「チャンネルを見る」「アプリコマンドを使う」（Use Application Commands）が必要です。
- `/horaro` は通常のメンバーも利用できます。
- `/horaro-admin` は既定で「サーバーの管理」（Manage Server）が必要です。変更する場合は **サーバー設定 → 連携サービス → このBot** で利用者・ロール・チャンネルを設定します。これはBotに付与する権限ではありません。

コマンドはBotの起動時に自動登録されます。表示されない場合は、Botがサーバーにインストールされていることと、ユーザーのコマンド利用権限を確認してください。通知だけ届かない場合は、通知先チャンネルでのBotの権限を確認してください。

## 注意

- 通知は登録先の予定時刻に基づきます。実際の進行が遅れていても、主催者が公開スケジュールを更新するまでは反映されません。
- RiJ 公式は公開 JSON の形式バージョン 2 に対応しています。イベント開始時刻に各プログラムの予定タイムと準備時間を積み上げて開始時刻を計算します。形式が変わった場合は取得失敗として扱い、最後に取得できた予定表を使います。
- 接続先は horaro.net（horaro.org の URL も可）と `rtain.jp/schedule/` に限ります。任意のセルフホスト Horaro や独自形式の JSON は登録できません。
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
