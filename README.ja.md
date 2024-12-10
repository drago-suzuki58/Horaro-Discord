# Horaro Discord Bot

このBotは[Horaro](https://horaro.org)でホスティングされたイベントスケジュールをDiscordで確認し、あなたの友人とイベントを楽しむために作成されたものです。

Other Language LEADME  
[English](README.md)

## 特徴

- Discordのイベント機能に登録してサーバーに通知
- リマインダーを設定して配信の見逃しの防止
- 今行われているイベントプログラムをDiscordから離れずに確認

## 使用方法

このリポジトリをフォークやクローンして

```sh
git clone https://github.com/drago-suzuki58/Horaro-Discord.git
```

pipまたはpoetryで

```sh
pip install -r requirements.txt
```

か

```sh
poetry install
```

をして依存関係をインストールしてください。

そして、`.env.EXAMPLE`を`.env`にコピーし、トークンなど内容を編集してから保存してください。

準備が整い、main.pyを実行すればBotを動作させられます。

## コマンド

- `/add_event`  
  入力されたURLからHoraroイベントを追加します。  
  `notice`を追加すればリマインダーの時間を分単位で指定できます。

- `/change_channel`  
  登録済みのHoraroイベントのリマインダーをするチャンネルを変更できます。  
  該当するHoraroイベントのURLと変更先のチャンネルID(数字)を入力してください。

- `/change_notice`  
  登録済みのHoraroイベントのリマインダーの時間を変更できます。  
  該当するHoraroイベントのURLと変更後のリマインダー時間を分単位で入力してください。

- `/change_url`  
  登録済みのHoraroイベントのURL参照先を変更できます。  
  該当するHoraroイベントの古いURLと変更後のURLを入力してください。

- `/create_server_event`  
  登録済みのHoraroイベントのURLから、Discordのサーバーイベントを作成できます。  
  該当するHoraroイベントのURLを入力してください。

- `/create_server_event_all`  
  コマンドが実行されたサーバーで登録済みのHoraroイベント全てから一括でDiscordのサーバーイベントを作成できます。

- `/get_now_program`  
  登録済みにHoraroイベント全ての中から、現在行われているプログラムを抽出し、10個まで表示します。

- `/list_events`  
  コマンドが実行されたサーバーに登録されているHoraroイベントのリストを表示します。  

- `remove_event`  
  登録済みのHoraroイベントから指定されたURLと一致するものを削除します。  
  確認機能付きです。

- `/update_schedule`  
  コマンドが実行されたサーバーに登録されているHoraroイベントのデータを、一括でHoraroに掲載されている最新の情報に更新します。
  デフォルトでは1日ごとに自動で最新情報に更新されますが、必要な場合手動更新も可能です。
