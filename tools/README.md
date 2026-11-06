# ビルド・配布

ルートのREADMEに従ってWindowsのPython 3.11環境とrequirements-build.txtを準備し、build.ps1を実行します。隣接する別プロジェクトのフォルダは不要です。

Python版は、ルートの *.py・start.cmd・requirements.txt・login-credentials.example.json と、同じ依存パッケージを入れた再配布可能なPython環境をruntime/として用意します。個人設定・data/・文書は入れません。

`package_release.py --exe EXEフォルダ --python PYTHON版フォルダ --out 出力先` で、プログラムと説明書・ライセンスを分けた4つのZIPとSHA256SUMS.txtを作成します。入力には既に個人データを除外した配布専用フォルダを指定してください。既存ZIPは上書きしません。

リリース前に、両版の起動・改名・一覧・フィルターを確認し、第三者ライセンスの版を同梱物に合わせて更新します。外部TesseractやEdgeは同梱しません。

1.0.5の初回GitHub登録では、検証済みのプログラムを再ビルドせず、LICENSEと第三者通知文を補完して再梱包しています。アプリ機能の変更はありません。
