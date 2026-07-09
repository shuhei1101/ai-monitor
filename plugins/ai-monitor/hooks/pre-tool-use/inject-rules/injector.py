"""PreToolUse フック: 対象ファイルにマッチするルール .md を Claude へ自動注入する。"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

LOG_TAG      = "inject_rules"
TARGET_TOOLS = ("Edit", "Write", "Read")

RULES_DIR         = pathlib.Path(__file__).resolve().parent / "rules"  # .md ルールフォルダの置き場所（テンプレート）
CACHE_DIR         = pathlib.Path(__file__).resolve().parent / "cache"  # URL 展開済みルール + メタの集約先
CACHE_RULES_DIR   = CACHE_DIR / "rules"                  # rules/ と同じ構造で URL 展開済み .md を配置
CACHE_SCAN_PATH   = CACHE_DIR / "scan_cache.json"        # スキャン結果（旧 rules/cache.json の移設先）
CACHE_EXPIRES_PATH = CACHE_DIR / "expires_at.txt"        # キャッシュ全体の有効期限（UNIX タイム）
TOKEN_DIR         = pathlib.Path.home() / ".claude" / "tokens" / "dev-kit" / "rules"  # セッショントークン保存先（プラグイン別）

# 1回の注入で許可する最大文字数（Claude の additional_context 上限）
CHAR_LIMIT = 10000
# 分割注入時に最低確保する body 文字数（これ未満なら分割せず次ブロックで打ち切る）
MIN_PARTIAL_CHARS = 200

# URL 埋め込み構文 @`URL`
URL_PLACEHOLDER_RE = re.compile(r"@`(https?://[^`]+)`")
# 1 URL の展開上限（超過分は ...(truncated) で切る）
MAX_URL_CHARS = 20000
# キャッシュ全体の TTL（秒）。期限切れで cache/ を丸ごと作り直す
CACHE_TTL_SECONDS = 1800
# fetch のタイムアウト（秒）
FETCH_TIMEOUT = 10
# Jekyll などの YAML front matter を先頭から剥がすための正規表現
_YAML_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)


def _eprint(msg: str) -> None:
    sys.stderr.write(f"[{LOG_TAG}] {msg}\n")


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """glob パターンを正規表現にコンパイルする。** はディレクトリ区切りをまたぐ。

    例:
      "**/foo.py"  → "src/bar/foo.py", "foo.py" にマッチ
      "src/*.py"   → "src/main.py" にマッチ、"src/sub/main.py" には非マッチ
      "{a,b}.py"   → "a.py", "b.py" にマッチ
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            parts.append(".*")          # ** = 区切りをまたぐ任意パス
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1                  # **/ の / を読み飛ばす
        elif c == "*":
            parts.append("[^/]*")       # * = 区切り以外の任意文字列
            i += 1
        elif c == "?":
            parts.append("[^/]")        # ? = 区切り以外の任意1文字
            i += 1
        elif c == "[":
            parts.append(r"\[")
            i += 1
        elif c == "]":
            parts.append(r"\]")
            i += 1
        elif c == "{":
            parts.append("(?:")         # { → 非キャプチャグループ開始
            i += 1
        elif c == "}":
            parts.append(")")
            i += 1
        elif c == ",":
            parts.append("|")           # , → 選択（{a,b} の区切り）
            i += 1
        else:
            parts.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def _match_any(pattern: str, candidates: list[str]) -> bool:
    """candidates のいずれかが pattern にマッチするか判定する。"""
    regex = _glob_to_regex(pattern)
    return any(regex.match(c) for c in candidates)


def _parse_frontmatter(content: str) -> dict | None:
    """先頭の --- フロントマターを行ベースで解析し paths を返す。

    paths の値はクォート必須。クォートなしのエントリは無視する。
    YAML safe_load は `- **/*.py` のようなクォートなし glob をエイリアス参照と
    解釈して壊すため、フロントマターは行単位で独自に解析する。
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None

    paths: list[str] = []
    current_key: str | None = None

    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_key == "paths":
                val = stripped[2:].strip()
                # クォートで囲まれた値のみ受け付ける
                if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
                    paths.append(val[1:-1])
            continue
        if ":" in stripped:
            key, _, rest = stripped.partition(":")
            key = key.strip().lower()
            rest = rest.strip()
            current_key = key
            if key == "paths" and rest and not rest.startswith("["):
                # paths: "foo.py" 形式のインライン値
                if len(rest) >= 2 and rest[0] in "\"'" and rest[-1] == rest[0]:
                    paths.append(rest[1:-1])
                current_key = None
            elif key != "paths":
                current_key = None

    return {"paths": paths} if paths else None


def _scan_rules() -> list[dict]:
    """RULES_DIR 配下の .md を走査してフロントマターを解析し、エントリ一覧を返す。"""
    entries: list[dict] = []
    for md in sorted(RULES_DIR.rglob("*.md")):
        try:
            content = md.read_text(encoding="utf-8")
        except Exception as e:
            _eprint(f"読み込みエラー ({md}): {e}")
            continue
        frontmatter = _parse_frontmatter(content)
        if not frontmatter:
            continue
        entries.append({
            "rel_path": str(md.relative_to(RULES_DIR)).replace("\\", "/"),
            "paths": frontmatter["paths"],
        })
    return entries


def _load_entries() -> list[dict]:
    """スキャン結果キャッシュがあればそれを使い、なければ _scan_rules() で生成して保存する。"""
    if CACHE_SCAN_PATH.exists():
        try:
            data = json.loads(CACHE_SCAN_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as e:
            _eprint(f"scan_cache 読み込みエラー: {e}")
    entries = _scan_rules()
    try:
        CACHE_SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_SCAN_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _eprint(f"scan_cache 書き込みエラー: {e}")
    return entries


def _normalize_github_url(url: str) -> str:
    """GitHub の blob / wiki ページ URL を raw.githubusercontent.com の URL に変換する。

    対応パターン:
    - github.com/{owner}/{repo}/blob/{rest}    → raw.githubusercontent.com/{owner}/{repo}/{rest}
    - github.com/{owner}/{repo}/wiki/{page}    → raw.githubusercontent.com/wiki/{owner}/{repo}/{page}.md
      （末尾 .md は補完。Wiki UI URL でも raw markdown を取得できる）

    どちらにもマッチしなければ url をそのまま返す。
    """
    m = re.match(
        r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/blob/(.+)$",
        url,
    )
    if m:
        owner, repo, rest = m.group(1), m.group(2), m.group(3)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"
    m = re.match(
        r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/wiki/(.+?)(?:\.md)?$",
        url,
    )
    if m:
        owner, repo, page = m.group(1), m.group(2), m.group(3)
        return f"https://raw.githubusercontent.com/wiki/{owner}/{repo}/{page}.md"
    return url


class _HTMLTextExtractor(HTMLParser):
    """script/style 系を除外しつつテキストノードを収集する HTMLParser。"""

    # 子要素ごと丸ごとスキップしたい要素のみ。void タグ (meta/link 等) は depth が戻らないので含めない
    SKIP_TAGS = {"script", "style", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0:
            # 隣接テキスト同士がくっつかないよう、タグ境界で改行を入れる（後段で空行は圧縮）
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <br/> 等の self-closing は depth に影響させない
        if self._skip_depth == 0:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif self._skip_depth == 0:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _html_to_text(html: str) -> str:
    """HTML から script/style 等を除いてテキストのみ抽出し、連続空行を圧縮する。"""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        text = parser.get_text()
    except Exception as e:
        _eprint(f"HTML パースエラー: {e}")
        # フォールバック: タグ単純除去
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    lines = [line.strip() for line in text.splitlines()]
    out_lines: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                out_lines.append("")
            blank = True
        else:
            out_lines.append(line)
            blank = False
    return "\n".join(out_lines).strip()


def _percent_encode_url(url: str) -> str:
    """URL の path / query に含まれる非 ASCII 文字を percent-encoding する。

    urllib.request は ASCII URL しか受け付けないため、日本語などを含む URL は
    送信前に各部を quote する必要がある。スキーム・ホストは触らない。
    """
    parts = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parts.path, safe="/%")
    safe_query = urllib.parse.quote(parts.query, safe="=&%")
    return urllib.parse.urlunsplit(parts._replace(path=safe_path, query=safe_query))


def _fetch_url_text(url: str) -> str:
    """URL から本文テキストを取得する。github.com は raw に変換、HTML はタグ除去する。"""
    fetch_url = _percent_encode_url(_normalize_github_url(url))
    req = urllib.request.Request(fetch_url, headers={"User-Agent": "inject_rules/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        raw = resp.read()
        ctheader = resp.headers.get("Content-Type", "") or ""

    ctype = ctheader.split(";")[0].strip().lower()
    charset = "utf-8"
    for part in ctheader.split(";")[1:]:
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part[len("charset="):].strip().strip('"').strip("'") or "utf-8"
    text = raw.decode(charset, errors="replace")

    # raw.githubusercontent.com に変換済みのものはプレーンテキスト（markdown）想定
    if "raw.githubusercontent.com" in fetch_url:
        # Jekyll などの YAML front matter が先頭に付いていたら剥がす（プロンプトに混ざるのを防ぐ）
        return _YAML_FRONTMATTER_RE.sub("", text, count=1).strip()
    if ctype.startswith("text/html") or ctype == "application/xhtml+xml":
        return _html_to_text(text)
    return text.strip()


def _resolve_url_placeholders(content: str) -> str:
    """`@`URL`` を見つけて取得テキストを下に挿入する（元行は残す）。

    fetch 失敗時は `<!-- fetch failed: ... -->` を残し、注入処理は止めない。
    """

    def _replace(match: re.Match[str]) -> str:
        url = match.group(1)
        try:
            text = _fetch_url_text(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            return f"{match.group(0)}\n<!-- fetch failed: {url} ({e}) -->"
        except Exception as e:  # 想定外も握って注入自体は止めない
            _eprint(f"fetch 想定外エラー ({url}): {e}")
            return f"{match.group(0)}\n<!-- fetch failed: {url} ({e}) -->"
        if len(text) > MAX_URL_CHARS:
            text = text[:MAX_URL_CHARS] + "\n\n...(truncated)"
        # 取得元 URL をメタ情報に含めた md コードフェンスで包む（境界と出典が一目で分かる）
        # フェンスは 5 連バッククォート: 取得内容に ``` や ```` が含まれても閉じ判定されないようにする
        return f"{match.group(0)}\n\n`````md:{url}\n{text}\n`````"

    return URL_PLACEHOLDER_RE.sub(_replace, content)


def _build_cache_rules(entries: list[dict]) -> None:
    """rules/ 配下の .md を URL 展開して cache/rules/ 配下に書き出す。既存があればスキップ。"""
    for entry in entries:
        rel = entry["rel_path"]
        src = RULES_DIR / rel
        dst = CACHE_RULES_DIR / rel
        if dst.exists():
            continue
        try:
            content = src.read_text(encoding="utf-8")
        except Exception as e:
            _eprint(f"ルール読み込みエラー ({rel}): {e}")
            continue
        expanded = _resolve_url_placeholders(content)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(expanded, encoding="utf-8")
        except Exception as e:
            _eprint(f"cache 書き込みエラー ({rel}): {e}")


def _ensure_cache_fresh() -> list[dict]:
    """TTL を確認し、期限切れなら cache/ を丸ごと作り直して entries を返す。"""
    expired = True
    if CACHE_EXPIRES_PATH.exists():
        try:
            expires_at = int(CACHE_EXPIRES_PATH.read_text(encoding="utf-8").strip())
            if time.time() <= expires_at:
                expired = False
        except Exception as e:
            _eprint(f"expires_at 読み込みエラー: {e}")
    if expired and CACHE_DIR.exists():
        try:
            shutil.rmtree(CACHE_DIR)
        except Exception as e:
            _eprint(f"cache 削除エラー: {e}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_RULES_DIR.mkdir(parents=True, exist_ok=True)

    entries = _load_entries()
    _build_cache_rules(entries)

    try:
        CACHE_EXPIRES_PATH.write_text(
            str(int(time.time() + CACHE_TTL_SECONDS)),
            encoding="utf-8",
        )
    except Exception as e:
        _eprint(f"expires_at 書き込みエラー: {e}")
    return entries


def _load_token(path: pathlib.Path) -> dict:
    """セッショントークンファイルを読み込む。存在しないか壊れていれば空 dict を返す。"""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        _eprint(f"トークンパースエラー ({path.name}): {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _save_token(path: pathlib.Path, data: dict) -> None:
    """セッショントークンをファイルに書き込む。"""
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _eprint(f"トークン書き込みエラー ({path.name}): {e}")


def _split_body(content: str, offset: int = 0) -> str:
    """フロントマターを除いた本文を返す。offset が指定された場合は先頭 offset 文字をスキップする。"""
    if not content.startswith("---"):
        body = content.lstrip("\n")
    else:
        lines = content.splitlines(keepends=True)
        count = 0
        end_index = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                count += 1
                if count == 2:
                    end_index = i + 1
                    break
        if count < 2:
            body = content.lstrip("\n")
        else:
            body = "".join(lines[end_index:]).lstrip("\n")
    # offset 分スキップして残りを返す
    return body[offset:]


def _render_injection(blocks: list[dict], **ctx: object) -> str:
    """inject_message.j2 テンプレートをレンダリングして注入テキストを生成する。

    blocks の各要素: {"abs_path": str, "patterns": list[str], "body": str}
    ctx に進捗変数 (remaining_count, loaded_files, total_files, packed_chars, total_chars) を渡すと
    テンプレート内の進捗セクションが展開される。
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        raise ImportError(
            f"jinja2 が見つかりません: {e}。`pip install jinja2` でインストールしてください。"
        ) from e
    _hooks_dir = pathlib.Path(__file__).resolve().parent
    env = Environment(
        loader=FileSystemLoader(str(_hooks_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("inject_message.j2")
    # テンプレートが常に参照する進捗変数のデフォルト値
    ctx.setdefault("remaining_count", 0)
    ctx.setdefault("loaded_files", 0)
    ctx.setdefault("total_files", 0)
    ctx.setdefault("packed_chars", "0")
    ctx.setdefault("total_chars", "0")
    return tmpl.render(blocks=blocks, **ctx)


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
    except Exception as e:
        _eprint(f"stdin パースエラー: {e}")
        return 0

    tool_name = data.get("tool_name", "")
    if tool_name not in TARGET_TOOLS:
        return 0

    file_path: str = (data.get("tool_input") or {}).get("file_path", "") or ""
    if not file_path:
        return 0

    # マッチング用に絶対パスと cwd 相対パスの両方を用意する
    norm: list[str] = [file_path.replace("\\", "/")]
    try:
        rel = pathlib.Path(file_path).resolve().relative_to(pathlib.Path(os.getcwd()).resolve())
        norm.append(str(rel).replace("\\", "/"))
    except (ValueError, OSError):
        pass

    entries = _ensure_cache_fresh()

    # マッチしたルールの rel_path を重複なし・順序保持で収集
    matched: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if any(_match_any(p, norm) for p in entry.get("paths", [])):
            r = entry["rel_path"]
            if r not in seen:
                seen.add(r)
                matched.append(r)

    if not matched:
        return 0

    session_id: str = data.get("session_id", "default")
    token_path = TOKEN_DIR / f"{session_id}.json"
    token_data = _load_token(token_path)

    # partial: 部分読み込み済みファイルのオフセット {rel_path: int}
    _partial = token_data.get("partial")
    partial_offsets: dict[str, int] = _partial if isinstance(_partial, dict) else {}

    # injected_rules: 完全読み込み済みファイルのリスト
    _rules = token_data.get("rules")
    injected_rules: list[str] = _rules if isinstance(_rules, list) else []

    # 未完了（完全未読 + partial残り）のファイルを抽出
    to_inject = [r for r in matched if r not in injected_rules]

    # 新規注入がなければ何も出力しない（全ルールが注入済み）
    if not to_inject:
        return 0

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    entry_paths_map = {entry["rel_path"]: entry.get("paths", []) for entry in entries}

    # ブロックを構築（partial がある場合はオフセットから読む）
    blocks: list[dict] = []
    remaining_total_chars = 0  # to_inject 全体の残り body 文字数合計（進捗表示用）
    for r in to_inject:
        abs_path = (RULES_DIR / r).as_posix()
        patterns = entry_paths_map.get(r, [])
        rule_content = ""
        try:
            rule_content = (CACHE_RULES_DIR / r).read_text(encoding="utf-8")
        except Exception as e:
            _eprint(f"ルール読み込みエラー ({r}): {e}")
        offset = partial_offsets.get(r, 0)      # 部分読み込みのオフセット（0なら先頭から）
        remaining_body = _split_body(rule_content, offset)  # 今回読む対象
        remaining_total_chars += len(remaining_body)
        blocks.append({
            "abs_path": abs_path,
            "patterns": [f"`{p}`" for p in patterns],
            "body": remaining_body,
            "rel_path": r,
            "offset": offset,
        })

    # CHAR_LIMIT に収まる分だけ貪欲にパック
    # 大きなファイルは部分的に含め、残りは partial として次回へ
    packed_blocks: list[dict] = []
    newly_completed: list[str] = []           # 今回完全読み終えたファイル
    new_partial_offsets: dict[str, int] = {}  # 今回部分読みになったファイル

    for i, block in enumerate(blocks):
        candidate = packed_blocks + [block]
        rendered = _render_injection(candidate)

        if len(rendered) <= CHAR_LIMIT:
            # 収まる → 完全追加
            packed_blocks.append(block)
            newly_completed.append(block["rel_path"])
        else:
            # 収まらない → 利用可能な body 文字数を計算して分割を試みる
            current_len = len(_render_injection(packed_blocks)) if packed_blocks else 0
            # 空 body でオーバーヘッドを計算
            overhead_block = {**block, "body": ""}
            overhead_len = len(_render_injection(packed_blocks + [overhead_block])) - current_len
            available_body_chars = CHAR_LIMIT - current_len - overhead_len

            if available_body_chars >= MIN_PARTIAL_CHARS:
                # 最低文字数以上確保できる → 部分注入して次回へ続きを残す
                partial_body = block["body"][:available_body_chars]
                packed_blocks.append({**block, "body": partial_body})
                new_partial_offsets[block["rel_path"]] = block["offset"] + available_body_chars
            elif i == 0:
                # 最初の1件から既にオーバーかつ MIN_PARTIAL_CHARS も確保できない
                # → CHAR_LIMIT 分だけ強制注入（無限ループ防止）
                partial_body = block["body"][:CHAR_LIMIT]
                packed_blocks.append({**block, "body": partial_body})
                new_partial_offsets[block["rel_path"]] = block["offset"] + CHAR_LIMIT
            # else: 前ブロックまでで打ち切り
            break

    # トークン更新: 完全読み込み済みリストと partial オフセットを更新
    token_data["rules"] = list(set(injected_rules) | set(newly_completed))
    # 完全読み込み済みを partial から削除し、新しい partial を追加
    updated_partial = {k: v for k, v in partial_offsets.items() if k not in newly_completed}
    updated_partial.update(new_partial_offsets)
    token_data["partial"] = updated_partial
    _save_token(token_path, token_data)

    # 進捗変数
    # remaining_count: 次回も処理が必要な件数（partial 中 + 未着手）
    remaining_count = len(new_partial_offsets) + (len(blocks) - len(packed_blocks))
    loaded_files = len(injected_rules) + len(newly_completed)
    total_files = len(injected_rules) + len(to_inject)
    packed_body_chars = sum(len(b["body"]) for b in packed_blocks)

    reason = _render_injection(
        packed_blocks,
        remaining_count=remaining_count,
        loaded_files=loaded_files,
        total_files=total_files,
        packed_chars=f"{packed_body_chars:,}",
        total_chars=f"{remaining_total_chars:,}",
    )
    decision = "deny" if remaining_count > 0 else "allow"

    # systemMessage: 完了・未完了を問わず常に件数を表示する
    if remaining_count > 0:
        progress_line = (
            f"  Loading: {loaded_files}/{total_files} ファイル / "
            f"{packed_body_chars:,}/{remaining_total_chars:,} 文字 — 残り {remaining_count} 未完了\n"
        )
    else:
        progress_line = f"  Loaded: {loaded_files}/{total_files} ファイル\n"
    packed_rel_paths = [b["rel_path"] for b in packed_blocks]
    system_msg = "[rules-injection]\n" + progress_line + "".join(f"  · {f}\n" for f in packed_rel_paths)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "additionalContext": reason,
        },
        "systemMessage": system_msg,
    }
    sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
