# Google Forms API 仕様調査（Phase 2.0）

本ドキュメントは Phase 2.1（プロジェクト管理 API）/ 2.2（Google Form 作成）/ 2.3（回答ポーリング）の実装方針を確定するための調査結果である。`requirements.md` §5（Google Forms 連携の実装方針）および §10（未確定事項）に対応する。

調査は Google Forms API v1（`https://forms.googleapis.com/v1/`）の公式ドキュメントを `WebFetch` で取得し、加えて公開資料を `WebSearch` でクロスチェックして整理した。引用元 URL は本ドキュメント末尾の「参照ドキュメント」節に集約した。

---

## 1. 結論サマリ（採用方式の早見表）

| 項目 | 採用方針 | 根拠節 |
|---|---|---|
| 候補日時の質問形式 | **matrix（`QuestionGroupItem` + `Grid` + `columns.type=CHECKBOX`）** | §2 / §8 |
| 代替案の用意 | 「日付ごとに複数選択チェックボックス質問を並べる」を**フォールバック**として実装可能性のみ確認（実装は不要） | §3 |
| 出席番号の質問形式 | **`TextQuestion`（短文）を採用し、サーバ側（`backend/app/services/polling.py`）で `int(...)` バリデーション**を行う（API が text validation を提供しないため） | §5 |
| ポーリング間隔 | **既定 60 秒（requirements.md §4.4 のまま）で問題なし** | §6 |
| 必要スコープ | `forms.body` / `forms.responses.readonly` / `drive.file` の 3 つ（Phase 1.3 ですでに確保済み） | §7 |

---

## 2. matrix（チェックボックスグリッド）作成可否

### 可否

**作成可能**。Google Forms API v1 は `QuestionGroupItem`（質問グループ項目）に `Grid`（グリッド）を組み合わせる形でグリッド型質問を表現する。`Grid.columns` には `ChoiceQuestion` を渡し、その `type` を `CHECKBOX`（複数選択）または `RADIO`（単一選択）から選べる。本ツールでは「候補日時枠の複数選択」が必要なため `CHECKBOX` を採用する。

### 根拠

- `Grid` 型定義：「`columns`: Required. Shared choices across all questions; only `RADIO` and `CHECKBOX` allowed.」（[Forms API リファレンス](https://developers.google.com/forms/api/reference/rest/v1/forms#Grid)）
- `QuestionGroupItem` の制約：「all questions in the group must be of kind `row`」（公式ガイド / `WebSearch` クロスチェック）
- `ChoiceQuestion.type` enum：`CHOICE_TYPE_UNSPECIFIED` / `RADIO` / `CHECKBOX` / `DROP_DOWN`

### 実装サンプル（採用方式：matrix）

`forms.batchUpdate` で 1 つの `QuestionGroupItem` を `createItem` する例。
行ラベル＝候補日（`2026-07-15` 等）、列＝時間枠ラベル（`16:00-16:20` 等）。

```json
{
  "requests": [
    {
      "createItem": {
        "location": { "index": 1 },
        "item": {
          "title": "参加可能な日時にチェックを入れてください（複数選択可）",
          "questionGroupItem": {
            "grid": {
              "columns": {
                "type": "CHECKBOX",
                "options": [
                  { "value": "16:00-16:20" },
                  { "value": "16:20-16:40" },
                  { "value": "16:40-17:00" }
                ]
              },
              "shuffleQuestions": false
            },
            "questions": [
              { "required": true, "rowQuestion": { "title": "2026-07-15" } },
              { "required": true, "rowQuestion": { "title": "2026-07-16" } },
              { "required": true, "rowQuestion": { "title": "2026-07-17" } }
            ]
          }
        }
      }
    }
  ]
}
```

### 既知の制約・注意

- グループ内 `questions[]` は **すべて `rowQuestion` 型に限定**（混在不可）
- `Grid.columns` は **全行で共通**（行ごとに別の列セットを持たせるならグループを分ける）
- `Question` の `required` は **行（`rowQuestion`）単位**で指定する。「全行必須」にするには各 row の `required: true` を明示する
- `forms.create` は `info.title` / `info.documentTitle` 以外を無視するため、**質問は必ず `batchUpdate` で追加**する
- 公式 Python サンプルでも「`create` → `batchUpdate` 2 段呼び出し」が標準（[Apps Script / Python tutorial 検索結果](https://github.com/fguogufe2/GoogleFormsAPITutorial/blob/main/readMe.md)）

---

## 3. 代替案（matrix が使えない場合）

**実装は不要だが、フォールバックとして可能性を確認しておく**。

仮に matrix の API が将来制限された場合 / 仕様変更があった場合は、**「日付ごとに 1 つの `CHECKBOX` 型 `ChoiceQuestion` を並べる」** 形に切り替えられる。1 日 = 1 質問になり、回答パース時のキーが「質問 = 日付」となるためコードは matrix 方式とほぼ等価。

### 代替案サンプル

```json
{
  "requests": [
    {
      "createItem": {
        "location": { "index": 1 },
        "item": {
          "title": "2026-07-15 の参加可能な時間枠",
          "questionItem": {
            "question": {
              "required": true,
              "choiceQuestion": {
                "type": "CHECKBOX",
                "options": [
                  { "value": "16:00-16:20" },
                  { "value": "16:20-16:40" },
                  { "value": "16:40-17:00" }
                ]
              }
            }
          }
        }
      }
    },
    {
      "createItem": {
        "location": { "index": 2 },
        "item": {
          "title": "2026-07-16 の参加可能な時間枠",
          "questionItem": {
            "question": {
              "required": true,
              "choiceQuestion": {
                "type": "CHECKBOX",
                "options": [
                  { "value": "16:00-16:20" },
                  { "value": "16:20-16:40" }
                ]
              }
            }
          }
        }
      }
    }
  ]
}
```

### 代替案の利点・欠点

| 観点 | matrix（採用） | 代替（日付ごと並列） |
|---|---|---|
| API 呼び出し回数 | 1 件の `createItem` | 候補日数ぶんの `createItem`（`batchUpdate` 内でまとめてOK） |
| 回答者の UX | 一画面で完結、コンパクト | 質問が縦に長くなる |
| レスポンス JSON | 各行が個別 `questionId` | 各日付質問が個別 `questionId` |
| 列（時間枠）が日付ごとに異なる場合 | グループを複数に分ける必要あり | 自然に表現可 |

要件上、時間枠定義は全日共通（`project.json` の `candidate_time_slots`）なので **matrix のほうが UX と API 効率の両面で優位**。

---

## 4. `forms.responses.list` レスポンス構造とパース方法

### `FormResponse` の上位構造

```json
{
  "formId": "string",
  "responseId": "string",
  "createTime": "RFC3339 timestamp",
  "lastSubmittedTime": "RFC3339 timestamp",
  "respondentEmail": "string (optional)",
  "answers": {
    "<questionId-1>": { /* Answer */ },
    "<questionId-2>": { /* Answer */ }
  },
  "totalScore": 0
}
```

### `Answer` の構造（テキスト系）

```json
{
  "questionId": "string",
  "grade": { /* 採点情報、本ツールでは未使用 */ },
  "textAnswers": {
    "answers": [
      { "value": "string" }
    ]
  }
}
```

- **`CHECKBOX` の回答**：選択肢ぶんだけ `textAnswers.answers[]` に `{ "value": "..." }` が並ぶ
- **`RADIO` / `DROP_DOWN`**：`textAnswers.answers[]` は要素 1 件
- **短文 `TextQuestion`**：同上、要素 1 件

### マトリクス（`QuestionGroupItem`）回答のパース

**最重要ポイント**：公式リファレンスは以下を明記している。

> The answer for each row of a `QuestionGroupItem` is represented as a separate `Answer`.

つまり **行（`rowQuestion`）ごとに別々の `questionId` が割り当てられる**。`answers` マップは「行（=候補日）→ チェックされた列（=時間枠）のリスト」の形になる。

#### サンプルレスポンス（matrix方式・候補日 3 日 × 時間枠複数）

```json
{
  "formId": "1AbCdEf...",
  "responseId": "ACYDBNgABC...",
  "createTime": "2026-06-28T15:30:12.345Z",
  "lastSubmittedTime": "2026-06-28T15:30:12.345Z",
  "answers": {
    "00000001": {
      "questionId": "00000001",
      "textAnswers": {
        "answers": [
          { "value": "1" }
        ]
      }
    },
    "00000002": {
      "questionId": "00000002",
      "textAnswers": {
        "answers": [
          { "value": "16:00-16:20" },
          { "value": "16:20-16:40" }
        ]
      }
    },
    "00000003": {
      "questionId": "00000003",
      "textAnswers": {
        "answers": [
          { "value": "16:40-17:00" }
        ]
      }
    },
    "00000004": {
      "questionId": "00000004",
      "textAnswers": { "answers": [] }
    }
  }
}
```

ここで `00000001` は出席番号質問の ID、`00000002`〜`00000004` は matrix の 3 行（候補日 3 日分）に対応する個別 ID。**API 側では「どの `questionId` が何月何日に対応するか」は返らないため、Form 作成時に `form.json` に対応表（`questionId` ↔ `row.title=日付`）を保存しておく必要がある**（Phase 2.2 の責務）。

`forms.get` を呼び直せば各 `Item.questionGroupItem.questions[].questionId` と `rowQuestion.title` のペアが取れるので、保存忘れ時のフェイルセーフとして利用可。

#### パースアルゴリズム（疑似コード）

```python
def parse_response(form_response: dict, form_meta: FormInfo) -> Response:
    answers = form_response["answers"]

    # 1. 出席番号
    sn_qid = form_meta.student_number_question_id
    raw_sn = answers[sn_qid]["textAnswers"]["answers"][0]["value"]
    student_number = int(raw_sn.strip())   # ★整数バリデーションは★こ★こ★

    # 2. 候補日×時間枠 → Availability[]
    availability = []
    for date_str, row_qid in form_meta.row_question_id_by_date.items():
        slot_labels = [
            a["value"]
            for a in answers.get(row_qid, {}).get("textAnswers", {}).get("answers", [])
        ]
        for label in slot_labels:
            start, end = label.split("-")  # "16:00-16:20" → ("16:00", "16:20")
            availability.append(Availability(
                date=date_str, start=start, end=end
            ))

    return Response(
        google_form_response_id=form_response["responseId"],
        submitted_at=form_response["lastSubmittedTime"],
        student_number=student_number,
        availability=availability,
    )
```

### ポーリングの差分検知

- `forms.responses.list` は `pageSize` / `pageToken` でページングし、フィルタ `timestamp >= <最後の取得時刻>` のような時間フィルタは公開されていない（リファレンス未記載）
- 実装では **すべて取得 → 既知の `responseId` 集合との差分を取る**方式が現実的
  - 既知 ID 集合の取得は `FileResponseRepository.get_known_form_response_ids()`（Phase 1.2 で骨格定義済み）

---

## 5. 整数バリデーション付き短文回答

### 結論

**Google Forms API v1 の `TextQuestion` は `validation` / `textValidation` フィールドを持たない**。`TextQuestion` の唯一のフィールドは `paragraph: boolean` のみ（[Forms API リファレンス Question/TextQuestion](https://developers.google.com/forms/api/reference/rest/v1/forms#TextQuestion)）。

したがって **Form 作成時点で「整数のみ入力可」をブラウザ側で強制することは API ではできない**。Web UI で人手作成すれば「数値であること」「整数であること」のバリデーションを設定できるが、それは Forms API では未公開のまま（複数のオープンソース調査、Issue Tracker でも要望が出ているが未実装）。

### 採用方針

- Form 作成時：`TextQuestion(paragraph=False)` + `Question.required=True` で「必須・短文」を作る
- 回答パース時：`int(raw_value.strip())` で整数変換を試み、失敗時はその回答を **「不正回答」として記録しスキップ**（`responses/<出席番号>` フォルダが作成されないため `status` API では「未受領」のまま）
- 不正検知時のユーザー通知方法は Phase 2.3 で詰める（ログ出力で十分か、UI に未受領理由を表示するか）

### 実装サンプル（採用方式：API 側バリデーションなし）

```json
{
  "createItem": {
    "location": { "index": 0 },
    "item": {
      "title": "出席番号（半角数字）",
      "description": "1〜40 のあなたの出席番号を入力してください",
      "questionItem": {
        "question": {
          "required": true,
          "textQuestion": { "paragraph": false }
        }
      }
    }
  }
}
```

### 代替案（採用しない）：`DROP_DOWN` ChoiceQuestion

`project.json` の `student_numbers: [1, 2, 3, ...]` を選択肢に展開した **DROP_DOWN ChoiceQuestion** にすれば API レベルで「クラス名簿の番号のみ」を強制できる。
ただし requirements.md §5.1 が「短文回答、整数バリデーション」と明記しているため、本ツールでは採用しない。将来 UX 改善の選択肢として残す。

---

## 6. ポーリング API のクォータ制限

### 公式クォータ表（2026 年 6 月時点 / `WebFetch` 確認）

| リクエスト種別 | 1 日あたり | 1 分あたり（プロジェクト） | 1 分あたり（ユーザー × プロジェクト） |
|---|---|---|---|
| Read requests | 無制限 | 975 | 390 |
| **Expensive read requests**（`forms.responses.list` を含む） | 無制限 | **450** | **180** |
| Write requests | 無制限 | 375 | 150 |

出典：[Forms API Usage limits](https://developers.google.com/workspace/forms/api/limits)

### 既定 60 秒間隔の妥当性

- 1 教師 = 1 ユーザーで `forms.responses.list` を 60 秒に 1 回 = **1 分あたり 1 リクエスト**
- 制限値 **180/min/user** の **0.56%** しか使わない → **十分安全**
- requirements.md §4.4 の既定 60 秒は変更不要

### 推奨対策

- `429 Too Many Requests` 受領時は truncated exponential backoff（`min((2^n)+random_ms, max_backoff)`, max は 32〜64 秒推奨）
- Phase 2.3 の `polling.sync_responses()` で 429 を捕捉し、最低 1 回はリトライする実装としておく（リトライ詳細は実装時判断）
- 複数プロジェクトを同時オープンするユースケースは現状想定しないが、もし出てきても 60 秒間隔 × N プロジェクトなら 5〜10 オープン程度までは余裕

---

## 7. 必要 scope の最終確認

### 確定する scope セット（変更なし、Phase 1.3 で既に取得済み）

| scope | 用途 | 取得サブステップ |
|---|---|---|
| `https://www.googleapis.com/auth/forms.body` | Form 作成・`batchUpdate` で質問追加 | Phase 1.3 |
| `https://www.googleapis.com/auth/forms.responses.readonly` | `forms.responses.list` / `forms.responses.get` | Phase 1.3 |
| `https://www.googleapis.com/auth/drive.file` | アプリ自身が作成した Form を Drive 上で扱う（Forms は実体が Drive ファイル） | Phase 1.3 |

### 用途別の最小セット（参考）

| ユースケース | 必要 scope |
|---|---|
| Form 作成のみ | `forms.body` + `drive.file` |
| 回答取得のみ | `forms.responses.readonly` |
| 本ツール（作成 + 回答取得） | 上記 3 つすべて |

### `drive.file` を選んだ理由

`drive.file` は **「このアプリが作成 / 開いた特定ファイルのみ」** に権限を限定するスコープで、教師の Drive 全体にアクセスせず最小権限。`drive` や `drive.readonly` は過剰スコープになる。requirements.md §2.1 の指定どおり。

---

## 8. 採用方式（Phase 2.1 / 2.2 / 2.3 の実装方針）

### Phase 2.2（Form 作成）の採用方式

| 質問 | 方式 | 実装上の決定 |
|---|---|---|
| 出席番号 | `TextQuestion(paragraph=False)` + `required=True` | API での整数バリデーションは未対応のため、サーバ側でパース時に `int()` する |
| 候補日 × 時間枠 | **`QuestionGroupItem` + `Grid(columns.type=CHECKBOX)`** | 行＝候補日、列＝時間枠ラベル。各 row に `required=True` を付ける |
| Form 作成順序 | `forms.create`（タイトルのみ）→ `forms.batchUpdate`（質問 2 件を `createItem` で追加） | 公式の標準パターン |
| `form.json` 保存項目 | `formId`, `responderUri`, `editUri`, `student_number_question_id`, `row_question_id_by_date: { "2026-07-15": "<qid>", ... }` | 回答パース時に必要 |

### Phase 2.3（回答ポーリング）の採用方式

| 項目 | 方式 |
|---|---|
| API 呼び出し | `forms.responses.list(formId=..., pageSize=...)`（全件取得 → 差分） |
| 差分検知 | 既知 `responseId` 集合との set 差分（`FileResponseRepository.get_known_form_response_ids`） |
| 整数バリデーション | サーバ側で `int(value.strip())`。失敗時は不正回答としてスキップ + ログ警告 |
| 保存先 | `responses/<出席番号>/<YYYYMMDD_HHMMSS>.json`（Phase 1.2 の Repository 骨格に準拠） |
| ポーリング間隔 | 既定 60 秒（クォータに対し十分余裕） |
| 429 リトライ | truncated exponential backoff（最低 1 回） |

### 採用理由（matrix を選んだ理由）

1. **API 公式サポート**：v1 で `QuestionGroupItem` + `Grid` が安定提供されている
2. **UX**：1 画面でまとめてチェックできる（保護者・生徒の負荷が低い）
3. **API 呼び出し効率**：候補日が N 日でも `createItem` は 1 件で済む
4. **レスポンスパースの明確さ**：行ごとに `questionId` が分かれるため、列との対応が単純な辞書ルックアップになる
5. **代替案との同型性**：仮に将来 matrix 廃止になっても、`form.json` のフィールド名さえ揃えれば代替案に切り替えやすい

### リスク・注意事項

| リスク | 対策 |
|---|---|
| `questionGroupItem.questions[].questionId` を作成時に保存し忘れる | Phase 2.2 のテストで `form.json` に `row_question_id_by_date` が必ず書かれていることを assert する |
| 行ごとの `questionId` が `batchUpdate` レスポンスで取得できないケース | `forms.get` で読み直すフォールバックを実装（要追加検証） |
| `lastSubmittedTime` のタイムゾーンが UTC 固定で、ファイル名のローカルタイムスタンプとずれる | ファイル名は受信時刻（ローカル `datetime.now()`）、Response 内部は API レスポンス値そのまま、で運用方針を分ける |
| 整数バリデーション失敗（保護者がフリーテキスト入力） | バリデーション失敗時はファイル保存しない + 警告ログ。Phase 2.3 のテストケースに含める |
| matrix の `Grid` で `shuffleQuestions: true` を誤って指定すると日付がランダム化される | デフォルト `false` を明示。Phase 2.2 のサンプル JSON にも `false` を書く |

---

## 9. Phase 2.1 / 2.2 / 2.3 着手前のチェックリスト

- [x] matrix 方式が API で実装可能であることを確認
- [x] 代替案（日付ごと並列）の構造もサンプル化済み
- [x] `forms.responses.list` のレスポンス構造と行 ID の挙動を把握
- [x] 整数バリデーションは API では不可、サーバ側で実装する方針を確定
- [x] クォータ上、60 秒ポーリングは安全と判定
- [x] scope は Phase 1.3 で取得済みのまま変更不要
- [x] 採用方式（matrix）と理由・リスクを明文化
- [ ] 実装着手前にユーザー承認を得る（**本サブステップは承認ポイント**）

---

## 10. 参照ドキュメント（情報源）

主な情報源は `WebFetch` で取得した Google 公式リファレンスである。各ページの主要内容は本ドキュメント本文に引用した。

| 参照先 | 用途 |
|---|---|
| <https://developers.google.com/forms/api/reference/rest/v1/forms> | `Item` / `QuestionItem` / `QuestionGroupItem` / `Grid` / `RowQuestion` / `ChoiceQuestion` / `TextQuestion` の各型定義 |
| <https://developers.google.com/forms/api/reference/rest/v1/forms.responses> | `FormResponse` / `Answer` / `TextAnswers` 構造、`QuestionGroupItem` の「行ごとに別 `questionId`」記述 |
| <https://developers.google.com/forms/api/reference/rest/v1/forms/batchUpdate> | `batchUpdate` リクエスト構造、`createItem` の `location.index` 仕様 |
| <https://developers.google.com/workspace/forms/api/limits> | クォータ表（Read / Expensive read / Write） |
| <https://developers.google.com/workspace/forms/api/guides/create-form-quiz> | `forms.create` の制約（`title` / `documentTitle` のみコピー） |
| <https://developers.google.com/workspace/forms/api/guides/update-form-quiz> | `batchUpdate` の使い方ガイド（質問追加例は薄い） |
| <https://googleapis.github.io/google-api-python-client/docs/dyn/forms_v1.forms.html> | Python クライアントの `create()` / `batchUpdate()` シグネチャ |
| <https://github.com/fguogufe2/GoogleFormsAPITutorial/blob/main/readMe.md> | サードパーティの実装サンプル（`create` → `batchUpdate` 2 段の通例を確認） |

### 未確認・要追加検証

- **未確認**：`batchUpdate` レスポンスで `questionGroupItem.questions[].questionId` が返るかどうか。公式リファレンスでは「`writeControl` と `requiredRevisionId` の応答仕様」のみ言及されており、生成 ID の返却挙動は実装時に実機検証が必要。返らない場合は Phase 2.2 内で `forms.get` を 1 回追加コールしてマッピング表を組み立てる
- **未確認**：`forms.responses.list` のレスポンスの並び順（`createTime` 昇順なのか降順なのか）。実装時に確認し、差分検知ロジックが順序に依存しないことを保証する
- **未確認**：401 / 403 / 429 各ステータスの実機挙動。Phase 2.3 でログ整備時に再確認

これらは Phase 2.2 / 2.3 の実装段階で実機確認するものとし、本フェーズでは「実装上の前提仕様」として明文化するに留める。
