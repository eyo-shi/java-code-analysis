# Java Code Analysis

任意の Java リポジトリを解析し、**Bolt 接続可能な Neo4j** に業務横断グラフを投入する CML AMP です。

## 概要

- **汎用 Java 解析 AMP**: 特定リポジトリに固定されていません
- **Deploy 時に `GIT_REPO_URL` を指定**して解析対象を決定
- **Config の `GIT_REPO_URL` を変更**すれば、同じ AMP で別リポジトリを解析可能
- **任意の Neo4j に出力可能**: neo4j-launcher、ローカル Neo4j、Neo4j Aura など Bolt URI で接続できるインスタンスに対応
- Spring MVC + MyBatis 構成の Java プロジェクトで最も多くのノードが自動抽出されます

## クイックスタート（CML）

1. 接続先の Neo4j が起動済みであることを確認（neo4j-launcher、ローカル、Aura など）
2. 本 AMP を CML プロジェクトにデプロイ（依存パッケージのインストールのみ自動実行）
3. **Project Settings → Advanced → Environment Variables** で以下を設定:

| 変数 | 必須 | 説明 |
|------|------|------|
| `GIT_REPO_URL` | はい* | 解析対象の Git リポジトリ URL |
| `GIT_REF` | いいえ | ブランチ/タグ（デフォルト: `main`） |
| `NEO4J_URI` | はい | 接続先 Neo4j の Bolt URI |
| `NEO4J_USERNAME` | いいえ | Neo4j ユーザー名（デフォルト: `neo4j`） |
| `NEO4J_PASSWORD` | いいえ | Neo4j パスワード（デフォルト: `Neo4jPass1234`） |

\* `SOURCE_PATH` を設定した場合は clone をスキップするため不要

4. **Jobs** ページから **Analyze and Ingest** ジョブを手動実行

### 解析対象リポジトリの変更

**Project Settings → Advanced → Environment Variables** で `GIT_REPO_URL`（および必要なら `GIT_REF`）を書き換え、**Analyze and Ingest** ジョブを再実行してください。

`PROJECT_ID` / `PROJECT_NAME` を省略した場合、リポジトリ URL から自動生成されます。別リポジトリに切り替えた際に Neo4j 上で別グラフとして管理したい場合は、`PROJECT_ID` も合わせて変更してください。

### 設定例

**CML + neo4j-launcher の場合:**

```
GIT_REPO_URL=https://github.com/terasolunaorg/terasoluna-tourreservation-mybatis3
GIT_REF=release/5.7.1.SP1.RELEASE
NEO4J_URI=bolt://neo4j-launcher-<id>:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<neo4j-launcher起動時のパスワード>
```

`<id>` は neo4j-launcher のブラウザ URL（`neo4j-launcher-<id>.ml....cloudera.site`）から取得します。`*.cloudera.site` はブラウザ用で、ジョブからの Bolt 接続には使えません。

**ローカル Neo4j の場合:**

```
GIT_REPO_URL=https://github.com/your-org/your-java-app.git
GIT_REF=main
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
```

### Neo4j 接続先の例

| 接続先 | `NEO4J_URI` の例 |
|--------|------------------|
| neo4j-launcher（CML 内） | `bolt://neo4j-launcher-<id>:7687`（クラスタ内サービス名） |
| ローカル Neo4j | `bolt://localhost:7687` |
| Neo4j Aura | `neo4j+s://xxxxx.databases.neo4j.io` |
| リモート Neo4j | `bolt://hostname:7687` |

## グラフノード

| ノード | 説明 | 主な取得元 |
|--------|------|-----------|
| `Business` | 業務 | Controller モジュール + i18n |
| `Screen` | 画面 | Spring MVC ビューパス |
| `Process` | プロセス | モジュール内画面の推論 |
| `BusinessConcept` | 業務概念 | `domain/model` の Java クラス |
| `DataEntity` | データエンティティ | ドメインモデルから推論 |
| `Database` / `Table` / `Column` | DB スキーマ | DDL SQL + JDBC 設定 |
| `FormField` | 画面フォーム項目 | `*Form.java` |
| `JavaClass` / `JavaMethod` | Java コード | `.java` |
| `SQL` / `Operation` | DB アクセス | MyBatis `*Repository.xml` |
| `Condition` / `BusinessRule` | バリデーション | `*Form.java` アノテーション + `*Validator.java` |
| `DesignDocument` / `Evidence` | ドキュメント・根拠 | README 等 |

## グラフリレーション（主要）

| リレーション | 意味 |
|-------------|------|
| `HAS_SCREEN` | Business → Screen |
| `IMPLEMENTED_BY` | Screen → JavaMethod |
| `HAS_FIELD` | Screen → FormField |
| `BINDS_TO` | FormField → Column |
| `VALIDATES` | Screen → Condition |
| `CHECKS` | Condition → Column |
| `WRITES` | SQL → Column（`operation` プロパティ: INSERT/UPDATE） |
| `INSERTS` / `UPDATES` / `DELETES` / `SELECTS` | SQL → Table |
| `CONTAINS` | Database → Table |
| `HAS_COLUMN` | Table → Column |

## 分析クエリ例

### ① 指定 DB のテーブルを更新する業務一覧

```cypher
// $dbLogicalName に論理 DB 名（例: tourreserve）を指定
MATCH (db:Database {logical_name: $dbLogicalName, project_id: $projectId})
      -[:CONTAINS]->(t:Table)
MATCH (q:SQL)-[:WRITES|UPDATES|INSERTS]->(t)
WHERE q.operation IN ['INSERT', 'UPDATE']
MATCH (repo:JavaMethod)-[:EXECUTES]->(q)
MATCH (svc:JavaMethod)-[:CALLS*1..4]->(repo)
MATCH (s:Screen)-[:IMPLEMENTED_BY]->(svc)
MATCH (b:Business)-[:HAS_SCREEN]->(s)
RETURN DISTINCT b.name AS business, s.name AS screen, t.name AS table,
       collect(DISTINCT q.operation) AS operations
ORDER BY business, screen
```

### ② 画面ごとの INSERT/UPDATE カラムとバリデーション条件

```cypher
MATCH (s:Screen {project_id: $projectId})
OPTIONAL MATCH (s)-[:IMPLEMENTED_BY]->(svc:JavaMethod)
      -[:CALLS*1..4]->(repo:JavaMethod)-[:EXECUTES]->(q:SQL)
      -[w:WRITES]->(c:Column)<-[:HAS_COLUMN]-(t:Table)<-[:CONTAINS]-(db:Database)
WHERE w.operation IN ['INSERT', 'UPDATE'] OR q.operation IN ['INSERT', 'UPDATE']
OPTIONAL MATCH (s)-[:VALIDATES]->(cond:Condition)-[:CHECKS]->(c2:Column)
RETURN s.name AS screen, db.logical_name AS database, t.name AS table,
       collect(DISTINCT c.name) AS written_columns,
       collect(DISTINCT {field: cond.field_name, rule: cond.rule_type,
                         constraint: cond.constraint, message: cond.name}) AS conditions
ORDER BY screen, database, table
```

### ③ 同一カラムを更新する画面間のバリデーション差分

```cypher
MATCH (s:Screen {project_id: $projectId})-[:VALIDATES]->(cond:Condition)
      -[:CHECKS]->(c:Column)<-[:HAS_COLUMN]-(t:Table)
MATCH (s2:Screen {project_id: $projectId})-[:IMPLEMENTED_BY]->(:JavaMethod)
      -[:CALLS*1..4]->(:JavaMethod)-[:EXECUTES]->(q:SQL)-[:WRITES]->(c)
WHERE s <> s2 AND q.operation IN ['INSERT', 'UPDATE']
WITH c, t, collect(DISTINCT {screen: s.name, field: cond.field_name,
    rule: cond.rule_type, constraint: cond.constraint, message: cond.name}) AS validations
WHERE size(validations) > 1
RETURN t.name AS table, c.name AS column, validations
ORDER BY table, column
```

## サンプル Cypher

| 変数 | 必須 | デフォルト | 説明 |
|------|------|-----------|------|
| `GIT_REPO_URL` | はい* | — | 解析対象 Git URL |
| `GIT_REF` | いいえ | `main` | clone ブランチ/タグ |
| `NEO4J_URI` | はい | — | Neo4j Bolt URI |
| `NEO4J_USERNAME` | いいえ | `neo4j` | Neo4j ユーザー名 |
| `NEO4J_PASSWORD` | いいえ | `Neo4jPass1234` | Neo4j パスワード |
| `CLONE_DIR` | いいえ | `/tmp/source` | clone 先 |
| `SOURCE_PATH` | いいえ | — | ローカルパス指定時は clone 不要 |
| `PROJECT_ID` | いいえ | リポジトリ名から自動 | Neo4j 再投入キー |
| `PROJECT_NAME` | いいえ | リポジトリ名から自動 | 表示名 |
| `EXCLUDE_DIRS` | いいえ | `.git,target,...` | 除外ディレクトリ |

## サンプル Cypher

```cypher
// プロジェクト内のノード種別ごとの件数
MATCH (n)
WHERE n.project_id = $projectId
RETURN labels(n)[0] AS label, count(*) AS count
ORDER BY count DESC
```

```cypher
// 業務 → 画面 → Java → SQL → テーブル
MATCH (b:Business)-[:HAS_SCREEN]->(s:Screen)
      -[:IMPLEMENTED_BY]->(svc:JavaMethod)-[:CALLS*1..3]->(repo:JavaMethod)
OPTIONAL MATCH (repo)-[:PERFORMS]->(op:Operation)-[:REALIZES]->(q:SQL)
OPTIONAL MATCH (repo)-[:EXECUTES]->(q2:SQL)
WITH b, s, svc, repo, coalesce(q, q2) AS q
OPTIONAL MATCH (q)-[:INSERTS|SELECTS|UPDATES|DELETES]->(t:Table)
RETURN b.name, s.name, svc.qualified_name, repo.qualified_name, q.operation, t.name
LIMIT 20
```

## ローカル実行

```bash
pip install -r 0_session-install-dependencies/requirements.txt

export GIT_REPO_URL=https://github.com/your-org/your-java-app.git
export GIT_REF=main
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=Neo4jPass1234

python3 1_session-analyze-ingest/analyze_ingest.py
```

ローカルディレクトリを直接解析する場合:

```bash
export NEO4J_URI=bolt://localhost:7687
export SOURCE_PATH=/path/to/your-java-project
python3 1_session-analyze-ingest/analyze_ingest.py
```

---

# Java Code Analysis (English)

A CML AMP that analyzes any Java repository and ingests a cross-cutting business graph into **any Neo4j instance reachable via Bolt**.

## Overview

- **Generic Java analysis AMP**: not tied to a specific repository
- **Set `GIT_REPO_URL` at deploy time** to choose the analysis target
- **Change `GIT_REPO_URL` in Configuration** later to analyze a different repository with the same AMP
- **Works with any Neo4j**: neo4j-launcher, local Neo4j, Neo4j Aura, or any instance with a Bolt URI
- Most nodes are extracted automatically from Spring MVC + MyBatis Java projects

## Quick Start (CML)

1. Ensure the target Neo4j instance is running (neo4j-launcher, local, Aura, etc.)
2. Deploy this AMP to a CML project (only dependency installation runs automatically)
3. Set the following in **Project Settings → Advanced → Environment Variables**:

| Variable | Required | Description |
|----------|----------|-------------|
| `GIT_REPO_URL` | Yes* | Git repository URL to analyze |
| `GIT_REF` | No | Branch or tag (default: `main`) |
| `NEO4J_URI` | Yes | Bolt URI of the target Neo4j instance |
| `NEO4J_USERNAME` | No | Neo4j username (default: `neo4j`) |
| `NEO4J_PASSWORD` | No | Neo4j password (default: `Neo4jPass1234`) |

\* Not required when `SOURCE_PATH` is set (clone is skipped)

4. Manually run the **Analyze and Ingest** job from the **Jobs** page

### Changing the Analysis Target Repository

Update `GIT_REPO_URL` (and `GIT_REF` if needed) in **Project Settings → Advanced → Environment Variables**, then re-run the **Analyze and Ingest** job.

If `PROJECT_ID` / `PROJECT_NAME` are omitted, they are derived from the repository URL. Change `PROJECT_ID` as well when you want a separate graph in Neo4j for a different repository.

### Configuration Examples

**CML + neo4j-launcher:**

```
GIT_REPO_URL=https://github.com/terasolunaorg/terasoluna-tourreservation-mybatis3
GIT_REF=release/5.7.1.SP1.RELEASE
NEO4J_URI=bolt://cml-neo4j-xxxxx.namespace:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=Neo4jPass1234
```

**Local Neo4j:**

```
GIT_REPO_URL=https://github.com/your-org/your-java-app.git
GIT_REF=main
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
```

### Neo4j Connection Examples

| Target | Example `NEO4J_URI` |
|--------|---------------------|
| neo4j-launcher (in CML) | `bolt://cml-neo4j-xxxxx.namespace:7687` |
| Local Neo4j | `bolt://localhost:7687` |
| Neo4j Aura | `neo4j+s://xxxxx.databases.neo4j.io` |
| Remote Neo4j | `bolt://hostname:7687` |

## Graph Nodes

| Node | Description | Primary Source |
|------|-------------|----------------|
| `Business` | Business capability | Controller modules + i18n |
| `Screen` | UI screen | Spring MVC view paths |
| `Process` | Business process | Inferred screen flows per module |
| `BusinessConcept` | Domain concept | `domain/model` Java classes |
| `DataEntity` | Logical data entity | Inferred from domain models |
| `Database` / `Table` / `Column` | DB schema | DDL SQL + JDBC config |
| `FormField` | Form input field | `*Form.java` |
| `JavaClass` / `JavaMethod` | Java code | `.java` files |
| `SQL` / `Operation` | DB access | MyBatis `*Repository.xml` |
| `Condition` / `BusinessRule` | Validation rules | `*Form.java` annotations + `*Validator.java` |
| `DesignDocument` / `Evidence` | Documentation / provenance | README, etc. |

## Graph Relationships (Key)

| Relationship | Meaning |
|-------------|---------|
| `HAS_SCREEN` | Business → Screen |
| `IMPLEMENTED_BY` | Screen → JavaMethod |
| `HAS_FIELD` | Screen → FormField |
| `BINDS_TO` | FormField → Column |
| `VALIDATES` | Screen → Condition |
| `CHECKS` | Condition → Column |
| `WRITES` | SQL → Column (`operation` property: INSERT/UPDATE) |
| `INSERTS` / `UPDATES` / `DELETES` / `SELECTS` | SQL → Table |
| `CONTAINS` | Database → Table |
| `HAS_COLUMN` | Table → Column |

## Analytical Query Examples

### ① Businesses that update tables on a given database

```cypher
// Set $dbLogicalName to the logical DB name (e.g. tourreserve)
MATCH (db:Database {logical_name: $dbLogicalName, project_id: $projectId})
      -[:CONTAINS]->(t:Table)
MATCH (q:SQL)-[:WRITES|UPDATES|INSERTS]->(t)
WHERE q.operation IN ['INSERT', 'UPDATE']
MATCH (repo:JavaMethod)-[:EXECUTES]->(q)
MATCH (svc:JavaMethod)-[:CALLS*1..4]->(repo)
MATCH (s:Screen)-[:IMPLEMENTED_BY]->(svc)
MATCH (b:Business)-[:HAS_SCREEN]->(s)
RETURN DISTINCT b.name AS business, s.name AS screen, t.name AS table,
       collect(DISTINCT q.operation) AS operations
ORDER BY business, screen
```

### ② INSERT/UPDATE columns and validation conditions per screen

```cypher
MATCH (s:Screen {project_id: $projectId})
OPTIONAL MATCH (s)-[:IMPLEMENTED_BY]->(svc:JavaMethod)
      -[:CALLS*1..4]->(repo:JavaMethod)-[:EXECUTES]->(q:SQL)
      -[w:WRITES]->(c:Column)<-[:HAS_COLUMN]-(t:Table)<-[:CONTAINS]-(db:Database)
WHERE w.operation IN ['INSERT', 'UPDATE'] OR q.operation IN ['INSERT', 'UPDATE']
OPTIONAL MATCH (s)-[:VALIDATES]->(cond:Condition)-[:CHECKS]->(c2:Column)
RETURN s.name AS screen, db.logical_name AS database, t.name AS table,
       collect(DISTINCT c.name) AS written_columns,
       collect(DISTINCT {field: cond.field_name, rule: cond.rule_type,
                         constraint: cond.constraint, message: cond.name}) AS conditions
ORDER BY screen, database, table
```

### ③ Validation differences across screens updating the same column

```cypher
MATCH (s:Screen {project_id: $projectId})-[:VALIDATES]->(cond:Condition)
      -[:CHECKS]->(c:Column)<-[:HAS_COLUMN]-(t:Table)
MATCH (s2:Screen {project_id: $projectId})-[:IMPLEMENTED_BY]->(:JavaMethod)
      -[:CALLS*1..4]->(:JavaMethod)-[:EXECUTES]->(q:SQL)-[:WRITES]->(c)
WHERE s <> s2 AND q.operation IN ['INSERT', 'UPDATE']
WITH c, t, collect(DISTINCT {screen: s.name, field: cond.field_name,
    rule: cond.rule_type, constraint: cond.constraint, message: cond.name}) AS validations
WHERE size(validations) > 1
RETURN t.name AS table, c.name AS column, validations
ORDER BY table, column
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GIT_REPO_URL` | Yes* | — | Git URL to analyze |
| `GIT_REF` | No | `main` | Branch or tag to clone |
| `NEO4J_URI` | Yes | — | Neo4j Bolt URI |
| `NEO4J_USERNAME` | No | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | No | `Neo4jPass1234` | Neo4j password |
| `CLONE_DIR` | No | `/tmp/source` | Clone destination |
| `SOURCE_PATH` | No | — | Skip clone when set |
| `PROJECT_ID` | No | Auto from repo name | Re-ingestion key in Neo4j |
| `PROJECT_NAME` | No | Auto from repo name | Display name |
| `EXCLUDE_DIRS` | No | `.git,target,...` | Directories to exclude |

## Sample Cypher

```cypher
// Node counts by label within a project
MATCH (n)
WHERE n.project_id = $projectId
RETURN labels(n)[0] AS label, count(*) AS count
ORDER BY count DESC
```

```cypher
// Business → Screen → Java → SQL → Table
MATCH (b:Business)-[:HAS_SCREEN]->(s:Screen)
      -[:IMPLEMENTED_BY]->(svc:JavaMethod)-[:CALLS*1..3]->(repo:JavaMethod)
OPTIONAL MATCH (repo)-[:PERFORMS]->(op:Operation)-[:REALIZES]->(q:SQL)
OPTIONAL MATCH (repo)-[:EXECUTES]->(q2:SQL)
WITH b, s, svc, repo, coalesce(q, q2) AS q
OPTIONAL MATCH (q)-[:INSERTS|SELECTS|UPDATES|DELETES]->(t:Table)
RETURN b.name, s.name, svc.qualified_name, repo.qualified_name, q.operation, t.name
LIMIT 20
```

## Local Execution

```bash
pip install -r 0_session-install-dependencies/requirements.txt

export GIT_REPO_URL=https://github.com/your-org/your-java-app.git
export GIT_REF=main
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=Neo4jPass1234

python3 1_session-analyze-ingest/analyze_ingest.py
```

To analyze a local directory directly:

```bash
export NEO4J_URI=bolt://localhost:7687
export SOURCE_PATH=/path/to/your-java-project
python3 1_session-analyze-ingest/analyze_ingest.py
```
