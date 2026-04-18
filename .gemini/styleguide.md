# Gemini Code Assist スタイルガイド — kinako-mocchi

> このファイルは Gemini Code Assist が PR レビュー時に参照するプロジェクト固有の規約です。
> リポジトリ固有の意図的な設計を理解した上でレビューしてください。

## プロジェクト概要

YouTube テック解説チャンネル「きなこもっちーのテック深掘り」の自動制作パイプライン。
技術スタック: Python（ツール群）、TypeScript/React（Remotion 動画制作）、VOICEVOX（音声合成）

---

## コーディング規約

### Python（`tools/*.py`）

- 命名規則: snake_case（変数・関数）、PascalCase（クラス）
- インポート: 標準ライブラリ → サードパーティ → ローカルの順序
- 型ヒント: 新規関数には推奨（既存コードへの遡及追加は不要）
- エラーハンドリング: `requests` / `subprocess` の呼び出しには必ず例外処理を含める
- 終了コード: ツールスクリプトは成功時 `sys.exit(0)`、失敗時 `sys.exit(1)` を明示する
- エンコーディング: 日本語テキストを含む `open()` には `encoding="utf-8"` を必ず指定する
- タイムゾーン: `datetime.now()` には `timezone(timedelta(hours=9))` 等で JST を明示する
- GitHub CLI: `gh issue list` / `gh pr list` には `--limit 1000` を使用する（200件超の Issue が存在）

### TypeScript / Remotion（`remotion/src/**`）

- 命名規則: camelCase（変数・関数）、PascalCase（コンポーネント・型）
- `strictNullChecks` が有効のため null チェックを適切に行う
- `durationInFrames` は整数（小数は Remotion でエラーになる）
- `fullscreenCueIds` には **lineId**（数値文字列、例: `"014"`）を使用すること。sectionId（例: `"title_call"`）を渡すと正しく動作しない

---

## 意図的な設計（レビューで指摘不要なパターン）

以下はプロジェクトの設計上意図的であり、バグではありません。

### BGM ギャップ（0.3秒）

`assets/bgm/*.wav` の末尾に 0.3 秒のギャップが含まれることがあります。
VOICEVOX 音声との自然な繋ぎのための意図的なパディングです。

### 大容量メディアは R2 管理

`assets/` 配下で利用する大容量メディアファイル（PNG/WAV/MP4 など）は Git LFS ではなく Cloudflare R2 で管理します。
これらのファイルを Git に含める前提でレビューしないでください。必要な場合のみ prefetch で取得する運用です。
Git LFS ポインターファイルを前提にした説明や指摘は行わず、R2 管理への移行方針に従って判断してください。

Git で管理する画像は `assets/characters/`・`assets/backgrounds/`・`assets/effects/`・`docs/**` 配下の小サイズファイルのみです（`.gitattributes` 参照）。

### VOICEVOX speedScale = 1.1

音声生成時のスピードが 1.1 に設定されています。これは「1分≒400文字」の実測値に基づく調整済みの値です。

### pipeline_state.json の completed_steps リセット

`content/pipeline-state/*.json` の `completed_steps` は、別パイプライン（script→audio 等）に切り替わった際に自動リセットされます。
これは複数パイプライン実行時の状態管理の意図的な動作です。

### audio_file パスの `audio/` プレフィックス

`timed.json` 内の `audio_file` パスは `audio/V{ID}/filename.wav` 形式（`assets/` なし）です。
Remotion が `Config.setPublicDir("../assets")` を設定しているため、`assets/` を付けると二重パスになります。これは仕様です。

### `[wip]` コミット

セッション切れ対策の自動コミット（`[wip] 圧縮前自動コミット`）が含まれることがあります。
PR の品質は個別コミットではなく **最終的な diff 全体** で評価してください。

### fact_check_flags

台本 JSON（`content/scripts/*_script.json`）内の `fact_check_flags` フィールドはファクトチェック記録です。
数値・日付・固有名詞の裏付け状況を示す設計上必須のフィールドで、削除・省略は不可です。

---

## ファイル・ディレクトリ規約

### 動画 ID

すべての動画関連ファイルは `V{3桁ID}` 形式（例: `V001`, `V023`）を使用します。

### `content/meta/*.yaml`

各動画のメタデータファイルです。PR の diff に **他の動画 ID のファイル** が含まれる場合は指摘してください（squash マージによる退行リスク）。

### `content/pipeline-state/*.json`

パイプライン実行状態ファイル（自動管理）。このファイルはコードレビューの対象外です。

---

## レビュー対象外ファイル

以下は自動生成・外部データであり、コードレビュー不要です:

- `docs/pronunciation-dictionary.json` — 発音辞書（パイプライン自動更新）
- `content/analytics/**` — YouTube/SNS アナリティクスデータ（自動収集）
- `content/pipeline-state/**` — パイプライン実行状態（自動管理）
- `content/analytics/slack_canvas_state.json` — Slack Canvas 状態（自動管理）
- `remotion/src/data/*/imageMap.ts` — 画像マップ（スクリプト自動生成）

---

## PR 説明文の読み方

- **`## 設計意図・既知の警告`** セクション: 意図的な設計決定の説明。ここに記載された内容は誤検知です
- **`[wip]` コミット**: セッション保護用の自動コミット。PR の品質は全体の diff で評価してください
- **`Closes #N`**: 対応 Issue 番号（自動クローズ）
- **`fact_check: +N件`**: コミットメッセージ内のファクトチェックフラグ追加数の記録

---

## よくある誤検知パターン

| パターン | 実際の状況 | 対応 |
|---------|---------|------|
| LFS ファイルが小さすぎる（134バイト） | 正常な LFS ポインター | 指摘不要 |
| `audio_file` が `assets/` で始まっていない | 正しい設計（`assets/` なしが正） | 指摘不要 |
| `speedScale: 1.1` がハードコード | 調整済みの実測値 | 指摘不要 |
| `completed_steps: []` にリセット | パイプライン切り替えの正常動作 | 指摘不要 |
| コミットメッセージが `[wip]` 形式 | セッション保護コミット | 指摘不要 |
| `fact_check_flags` が大量 | 品質管理の仕組み（削除禁止） | 指摘不要 |
| `// eslint-disable-next-line @typescript-eslint/no-explicit-any` コメント（TypeScript） | Remotion の型定義が不完全なため許容 | 指摘不要 |
| JST タイムゾーン明示（`timedelta(hours=9)`） | クラウド環境（UTC）対策の必須実装 | 指摘不要 |
