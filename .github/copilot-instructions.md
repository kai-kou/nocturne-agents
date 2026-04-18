# GitHub Copilot コードレビュー指示 — kinako-mocchi

> このファイルは GitHub Copilot が PR レビューを行う際に参照するリポジトリ固有の規約です。
> 以下の規約と意図的な設計を理解した上でレビューしてください。

## プロジェクト概要

YouTube テック解説チャンネル「きなこもっちーのテック深掘り」の自動制作パイプライン。
技術スタック: Python（ツール群）、TypeScript/React（Remotion 動画）、VOICEVOX（音声合成）

---

## コミットメッセージ規約

フォーマット: `[V{動画ID}] {Phase名}: {概要}`

```
例:
[V001] research: AIエージェントリサーチ完了
[V001] script: 台本v1生成
[V001] audio: VOICEVOX音声生成完了
[daily] 07:00 project-sync: ステータス更新
[wip] 圧縮前自動コミット（2026-04-11 09:30）  ← セッション保護用、意図的
```

**注意**: `[wip]` コミットは Claude Code がセッション切れ対策で自動生成するものです。バグではありません。

---

## ブランチ命名規約

```
content/V{ID}-{テーマ}   — 動画コンテンツブランチ
claude/V{ID}-{Phase}-{ランダム文字列}  — パイプライン自動生成ブランチ
feat/{機能名}   — 機能開発
fix/{修正名}    — バグ修正
docs/{ドキュメント名}  — ドキュメント更新
```

---

## ファイルパス規約

### 音声ファイル（重要）

```
正: audio/V{ID}/filename.wav
誤: assets/audio/V{ID}/filename.wav  ← 二重パスになりバグ
```

**理由**: Remotion が `Config.setPublicDir("../assets")` を使用しているため、
`assets/` を付けると `../assets/assets/audio/...` という二重パスになります。
`timed.json` 内の `audio_file` フィールドが `assets/` で始まっている場合は **バグ** です。

### 動画メタデータ

`content/meta/V{ID}_meta.yaml` — 各動画のメタデータ。
**他の動画 ID のファイルが PR の diff に含まれる場合は必ず指摘してください**（squash マージによる退行リスク: L-032）。

### Remotion config.ts の fullscreenCueIds

`fullscreenCueIds` には **lineId**（数値文字列、例: `"014"`）を使用すること。
`"title_call"` / `"cta"` 等の sectionId を使うと正しく動作しません（L-039）。

---

## 意図的な設計（指摘不要なパターン）

| パターン | 理由 |
|---------|------|
| LFS ポインターファイル（134バイト） | クラウド環境では LFS バイナリ取得不可。フォールバックロジックで対応済み |
| BGM WAV ファイルの末尾 0.3 秒ギャップ | VOICEVOX 音声との自然な繋ぎのための意図的なパディング |
| `speedScale: 1.1` | 「1分≒400文字」の実測値に基づく調整済みパラメーター |
| `completed_steps: []` リセット | 別パイプライン開始時の意図的なリセット（L-037対策） |
| `[wip]` コミット | セッション切れ保護の自動コミット |
| `fact_check_flags` フィールド（台本JSON） | ファクトチェック品質管理の必須フィールド。削除・省略は不可 |
| `// eslint-disable-next-line @typescript-eslint/no-explicit-any` コメント（TypeScript） | Remotion の型定義が不完全なため許容 |
| JST タイムゾーン（`timedelta(hours=9)`） | クラウド環境（UTC）での誤動作防止の必須実装 |
| `--limit 1000`（gh CLI） | Issue 数が 200 件超のため必要。`--limit 50` では全件取得不可 |

---

## 品質基準（バグとみなすパターン）

### 台本 JSON（`content/scripts/*_script.json`）

```
必ずチェック:
- 全セリフの text が 100文字以内（超過はバグ）
- emotion フィールドの有効値: normal/neutral/excited/confused/sad/whisper/tsukkomi/teaching/gentle
- voicevox_speaker_id がキャラクターに対応していること
  もっちー: 12(ふつう)/32(わーい)/33(びくびく)/34(おこ)/35(びえーん)
  きなこ: 2(ノーマル)/0(あまあま)/6(ツンツン)/4(セクシー)/36(ささやき)/37(ヒソヒソ)
- 数値・日付・人名・企業名を含むセリフには fact_check_flags が必須
```

### メタデータ YAML（`content/meta/*.yaml`）

```
自動設定後のみ存在するフィールド（生成前は存在しなくてよい）:
- youtube_video_id: YouTube API でアップロード後に設定
- metadata_verified: true — 手動レビュー後に設定
- scheduled_publish_at: スケジュール設定後に設定
```

### Python スクリプト（`tools/*.py`）

```
バグとみなすパターン:
- open() で encoding= 未指定（日本語ファイル操作時）
- datetime.now() でタイムゾーン未指定
- except: pass（例外の握りつぶし）
- gh issue list / gh pr list で --limit が 1000 未満（または未指定）
- if/else 両ブランチに同一コード行が重複（DRY 原則違反）
- __import__() のインライン使用（PEP 8 違反）
- audio_file パスが assets/ で始まる（二重パスバグ）
```

---

## レビュー優先度

以下の優先順位でレビューしてください:

1. **セキュリティ** — APIキーのハードコード、認証情報の漏洩
2. **データ完全性** — 他動画の meta.yaml が意図せず変更されていないか（L-032）
3. **パス規約** — audio_file が `assets/` で始まっていないか（二重パスバグ）
4. **品質ゲート** — 台本の必須フィールド・emotion 有効値・文字数
5. **コード品質** — DRY原則・例外処理・エンコーディング指定

---

## レビュー対象外ファイル

以下は自動生成・外部データのためレビュー不要です:

- `docs/pronunciation-dictionary.json` — 発音辞書（自動更新）
- `content/analytics/**` — アナリティクスデータ
- `content/pipeline-state/**` — パイプライン状態ファイル
- `content/analytics/slack_canvas_state.json` — Slack Canvas 状態
- `remotion/src/data/*/imageMap.ts` — スクリプト自動生成の画像マップ

---

## PR 説明文の読み方

- **`## 設計意図・既知の警告`** セクション: 意図的な設計の説明。記載内容は誤検知です
- **`Closes #N`**: 対応 Issue 番号
- **`[wip]` コミット**: セッション保護用。PR 全体の diff で評価してください
- **`fact_check: +N件`**: ファクトチェックフラグ追加数の記録（削除しないでください）
