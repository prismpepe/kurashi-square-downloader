# くらしスクエア文書ダウンローダー

くらしスクエアの文書を一覧表示し、選択した文書をカテゴリー・年月別フォルダに保存するWindowsアプリです。Python版・exe版を共通ソースで管理します。

## ダウンロード

[Releases](https://github.com/prismpepe/kurashi-square-downloader/releases) から、利用する版のプログラムZIPと説明書・ライセンスZIPの両方をダウンロードしてください。

- 通常の利用：exe版を展開して `KurashiDownloader.exe` を実行します。
- Python版：実行環境を同梱したZIPを展開して `start.cmd` を実行します。
- GitHubが自動生成する「Source code」は開発用ソースです。Python実行環境は含みません。

## 主な機能

- サイト文書一覧・保存文書一覧を切り替え
- 手動指示による文書取得、更新確認、重複保存の抑止
- 本文・任意の外部OCRによる自動改名と、OCR不要の手動改名
- 任意の保存先、手動追加文書の登録
- カテゴリー・年月／期に基づく年度・文字検索のAND絞り込み
- 進捗表示、中止、ログイン設定

WindowsとMicrosoft Edgeが必要です。OCRには別途Tesseractと日本語データが必要ですが、テキストPDFの表題取得・手動改名には不要です。

## ソースから実行

WindowsのPython 3.11で確認しています。Python本体にはTkinterを含めてインストールしてください。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe launcher.py
```

初回起動時に設定ファイルを作成します。ログイン情報・ブラウザー状態・文書は各自の環境で作成され、リポジトリには含めません。

## 開発・ビルド

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\tools\build.ps1 -Python .\.venv\Scripts\python.exe
```

配布の作成方法は [tools/README.md](tools/README.md)、操作方法は [取扱説明書](docs/取扱説明書.txt) を参照してください。

## ライセンス

本体の独自コード・独自ドキュメントは [MIT License](LICENSE) です。
第三者ライブラリとその通知文は各権利者のライセンスが適用され、本体のMITライセンスによって置き換わりません。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。
くらしスクエアのサービス、名称、ダウンロード文書の権利は本ライセンスの対象外です。
