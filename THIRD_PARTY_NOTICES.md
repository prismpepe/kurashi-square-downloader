# 第三者ソフトウェアのライセンス

本体のMITライセンスは本プロジェクトの独自部分に適用します。同梱・利用する第三者ソフトウェアには、それぞれの著作権表示・ライセンス・免責条項が適用されます。原文は `third_party/licenses/` に保存しています。依存パッケージの版とメタデータは `third_party/components.json` に記録しています。

## 主な構成要素

- Beautiful Soup、pdfplumber、pdfminer.six、pyee、charset-normalizer、soupsieve等：MIT。
- Playwright、pytesseract：Apache-2.0。NOTICEも保持しています。
- pypdfium2：BSD-3-Clause / Apache-2.0等（ファイル別）。PDFiumと同梱依存物のBUILD_LICENSESも保持しています。
- Pillow：MIT-CMUおよびバイナリに同梱される第三者ライブラリの条件。
- Python / typing_extensions：PSFライセンス等。Python同梱通知文を保持しています。
- Tcl/Tk：各配布物のlicense.terms。
- Node.js：Playwrightが配布するdriver/LICENSE内のNode.jsおよび依存物のライセンス。
- cryptography：Apache-2.0またはBSD-3-Clause。配布物の付随ライセンスも保持しています。
- PyInstaller：GPL-2.0の配布例外等。この例外により生成したアプリ本体をMITで配布できます。PyInstaller自身をMITに変更するものではありません。
- Python版に含まれるpipのcertifi証明書データ：MPL-2.0。未変更のPEMデータを含むpip/_vendor/certifiディレクトリがPython版に同梱されています。MPL対象ファイルを変更した場合は、そのファイルに対するMPLの義務を維持してください。
- Tesseract：外部インストールを利用し、この配布物には含めません。別途配布する場合はその配布物の条件を確認してください。

## 配布時の扱い

プログラムZIPと、同じ版の説明書・ライセンスZIPを一組として配布してください。後者に本体LICENSEと第三者通知文の原文を収録します。第三者の著作権表示、Apache NOTICE、ライセンス本文を削除・改変しないでください。ライブラリを変更・追加した際は、版・原文・必要なソース提供条件を再確認してください。

## 参照元

- MIT: https://opensource.org/license/mit
- PyInstaller配布例外: https://pyinstaller.org/en/stable/license.html
- pypdfium2: https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing
- MPL-2.0: https://www.mozilla.org/MPL/2.0/

確認日：2026-11-06。実際に同梱するライブラリの通知文を優先します。
