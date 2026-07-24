---
template_version: 1.0.0
---

# Grafana

telemetry の可視化ダッシュボード / Web UI。
Loki / Prometheus / Tempo など複数のデータソースを 1 画面から横断表示できる。
本ページは Docker Compose で単一サービスとして起動し、datasource を自動プロビジョニングする使い方に絞って情報を集約する。

## 現在のバージョン情報

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| バージョン | `11.3.0` | 2026-07-24 時点最新 |
| ライセンス | AGPL-3.0 | - |
| 公式 URL | https://github.com/grafana/grafana | - |
| 公式ドキュメント | https://grafana.com/docs/grafana/latest/ | - |

## インストール手順

Docker Compose の 1 サービスとして起動する。

```yaml
services:
  grafana:
    image: grafana/grafana:11.3.0
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_AUTH_ANONYMOUS_ENABLED: "false"
      GF_SERVER_ROOT_URL: http://localhost:3000
    volumes:
      - ./provisioning:/etc/grafana/provisioning
```

datasource を自動登録するには `./provisioning/datasources/datasources.yaml` を用意する。

```yaml
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
```

起動後は `http://localhost:3000` にブラウザでアクセスし、`admin` / `admin` でログインする。

## API 一覧

バージョン: `11.3.0`

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| UI | [`Explore`](#explore) | datasource を切り替えたアドホック検索画面 | LogQL / PromQL / TraceQL 対応 |
| UI | [`Dashboards`](#dashboards) | ダッシュボード保存 + panel 配置 | JSON で export / import 可 |
| 設定 | [`datasources.yaml`](#datasourcesyaml) | datasource の自動プロビジョニング YAML | `/etc/grafana/provisioning/datasources/` 配下 |
| HTTP API | [`GET /api/datasources`](#get-apidatasources) | 登録済み datasource 一覧の取得 | 自動化用 |
| HTTP API | [`POST /api/datasources`](#post-apidatasources) | datasource の追加 | 自動化用 |
| 環境変数 | [`GF_SECURITY_ADMIN_USER`](#gf_security_admin_user) | 管理ユーザー名 | Docker 起動時に指定 |
| 環境変数 | [`GF_SECURITY_ADMIN_PASSWORD`](#gf_security_admin_password) | 管理ユーザーパスワード | Docker 起動時に指定 |
| 環境変数 | [`GF_AUTH_ANONYMOUS_ENABLED`](#gf_auth_anonymous_enabled) | 匿名アクセス許可 | 有効化するとログイン不要 |
| 環境変数 | [`GF_SERVER_ROOT_URL`](#gf_server_root_url) | 公開ルート URL | リバプロ配下やサブパス配置時に必要 |
| クエリ例 | [`LogQL クエリ例`](#logql-クエリ例) | Loki datasource の Explore で使う代表クエリ | サービス / エラー / JSON フィールド絞込 |

### `Explore`

datasource を切り替えてアドホックにクエリを叩く画面。
サイドバーの `Explore` から入り、上部で datasource（Loki / Prometheus / Tempo 等）を切り替え、クエリエディタで検索式を記述する。

Loki datasource を選ぶと LogQL、Prometheus datasource を選ぶと PromQL、Tempo datasource を選ぶと TraceQL を書ける。
Split View で 2 datasource を横並びに見られる（例: メトリクス異常時点のログを右ペインで確認）。

#### 主要操作

| 操作 | 説明 | 補足 |
| --- | --- | --- |
| クエリバー | LogQL / PromQL / TraceQL を書く場所 | `Shift+Enter` で実行 |
| 時間範囲セレクタ | 右上でクエリ対象の期間を指定 | `Last 5 minutes` 〜 カスタム範囲 |
| Live | tail モード（ストリーミング表示） | Loki datasource のみ |
| Split | 画面を左右に分割 | 別 datasource を並べる |
| Add to dashboard | 現クエリを panel としてダッシュボード化 | - |

### `Dashboards`

複数の panel（グラフ / ログ / スタット）を 1 画面にまとめて保存する。
左サイドバーの `Dashboards` から `New dashboard` で新規作成し、panel を追加してクエリと表示種別（Time series / Logs / Stat 等）を設定する。

JSON model として export / import できるため、`provisioning/dashboards/` にファイルを置いておくと起動時に自動読み込みされる。

### `datasources.yaml`

Grafana 起動時に datasource を自動登録するプロビジョニング YAML。
`/etc/grafana/provisioning/datasources/` 配下に置くと、コンテナ起動時に読み込まれる。

#### フィールド

| フィールド | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `apiVersion` | `int` | 必須 | - | プロビジョニングファイルのスキーマ版 | 現行は `1` 固定 |
| `datasources[].name` | `str` | 必須 | - | datasource 識別名 | UI と HTTP API で参照するキー |
| `datasources[].type` | `str` | 必須 | - | datasource 種別 | `loki` / `prometheus` / `tempo` 等 |
| `datasources[].url` | `str` | 必須 | - | 接続先 URL | コンテナ間なら `http://{service}:{port}` |
| `datasources[].access` | `'proxy' or 'direct'` | 任意 | `proxy` | アクセス方式 | proxy=Grafana サーバー経由 / direct=ブラウザ直接 |
| `datasources[].isDefault` | `bool` | 任意 | `false` | Explore デフォルト選択 | 複数あるうち 1 つだけ true にする |

パラメータ例:

```yaml
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
```

### `GET /api/datasources`

登録済み datasource の一覧を取得する HTTP エンドポイント。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| Basic 認証 | `str:str` | 必須 | - | 管理ユーザー名 / パスワード | `-u admin:admin` |

パラメータ例:

```bash
curl -s -u admin:admin http://localhost:3000/api/datasources
```

#### 戻り値

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `[].id` | `int` | datasource ID | 内部連番 |
| `[].uid` | `str` | datasource UID | panel JSON から参照する識別子 |
| `[].name` | `str` | 識別名 | プロビジョニングの `name` |
| `[].type` | `str` | 種別 | `loki` 等 |
| `[].url` | `str` | 接続先 URL | - |
| `[].isDefault` | `bool` | Explore デフォルト選択 | - |

戻り値例:

```json
[
  {"id": 1, "uid": "P8E80F9AEF21F6940", "name": "Loki", "type": "loki", "url": "http://loki:3100", "isDefault": true}
]
```

### `POST /api/datasources`

datasource を新規追加する HTTP エンドポイント。
プロビジョニング YAML を使わず実行時に追加したい場合に使う。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| Basic 認証 | `str:str` | 必須 | - | 管理ユーザー名 / パスワード | `-u admin:admin` |
| `name` | `str` | 必須 | - | 識別名 | 一意 |
| `type` | `str` | 必須 | - | datasource 種別 | `loki` 等 |
| `url` | `str` | 必須 | - | 接続先 URL | - |
| `access` | `'proxy' or 'direct'` | 任意 | `proxy` | アクセス方式 | - |
| `isDefault` | `bool` | 任意 | `false` | Explore デフォルト選択 | - |

パラメータ例:

```bash
curl -s -u admin:admin -H "Content-Type: application/json" \
  -X POST http://localhost:3000/api/datasources \
  -d '{"name":"Loki","type":"loki","url":"http://loki:3100","access":"proxy","isDefault":true}'
```

### `GF_SECURITY_ADMIN_USER`

管理ユーザー名を指定する環境変数。

| 項目 | 内容 |
| --- | --- |
| 型 | `str` |
| 既定 | `admin` |
| 補足 | 初回ログイン後も UI から変更可 |

### `GF_SECURITY_ADMIN_PASSWORD`

管理ユーザーのパスワードを指定する環境変数。

| 項目 | 内容 |
| --- | --- |
| 型 | `str` |
| 既定 | `admin` |
| 補足 | 本番運用では必ず変更する |

### `GF_AUTH_ANONYMOUS_ENABLED`

匿名アクセスを許可するかどうかを指定する環境変数。

| 項目 | 内容 |
| --- | --- |
| 型 | `bool` |
| 既定 | `false` |
| 補足 | `true` にするとログイン不要（社内ダッシュボード向け） |

### `GF_SERVER_ROOT_URL`

Grafana の公開ルート URL を指定する環境変数。

| 項目 | 内容 |
| --- | --- |
| 型 | `str` |
| 既定 | `http://localhost:3000` |
| 補足 | リバプロ配下やサブパス配置時に明示指定する |

### `LogQL クエリ例`

Explore で Loki datasource を選んだときに叩く代表的な LogQL クエリ。
Grafana 自体の使い方例として掲載する（LogQL 文法の詳細は Loki のページに委譲）。

| クエリ | 用途 | 補足 |
| --- | --- | --- |
| `{service_name="ai-monitor"}` | サービス名で全ログを絞る | ラベルマッチャ（完全一致） |
| `{service_name=~".+"} \|= "error"` | 全サービス横断で `error` を含むログを抽出 | `=~` は正規表現マッチャ・`\|=` は行フィルタ |
| `{service_name="ai-monitor"} \| json \| issue_number="123"` | JSON パースして特定 Issue のログを抽出 | `\| json` は JSON 展開・後続でフィールド絞込 |
