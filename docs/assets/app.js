/* ============================================================================
 * my-plugins docs 共通スクリプト
 *
 * docs/ 配下すべてのページで読み込む単一 JS。
 * 各機能は「対象 DOM が無ければ何もしない」形で並べており、
 * Mock demo / Jekyll 描画ページ / Wiki など、ページ種別を問わず同じファイルで動く。
 *
 * Markdown → HTML の変換は Jekyll 側で完了しているので、ここでは行わない。
 *
 * 提供する機能:
 *   1.  パンくずリスト     ... [data-breadcrumb] があれば URL 階層から自動生成
 *   2.  テーブルソート     ... table にヘッダクリックで昇降ソートを付与
 *   3.  テーブルフィルタ   ... table 上部に検索ボックスを差し込み行を絞り込み
 *   4.  見出しアンカー     ... h2-h4 に # リンクを追加、クリックで URL をコピー
 *   5.  コードコピー       ... pre 右上に「コピー」ボタン
 *   6.  MD ダウンロード   ... [data-md-download] を raw MD URL に張り替える
 *   7.  トップに戻る       ... [data-back-to-top] のボタンをスクロール量で表示切替
 *   8.  目次サイドバー     ... [data-toc] に h2/h3 を並べ、現在位置ハイライト
 *   9.  ダークモード切替   ... [data-theme-toggle] で light/dark 切替、localStorage 保存
 *   10. Mermaid 自動描画   ... code.language-mermaid をレンダリング
 *   11. コード言語ラベル   ... pre 左上に言語名（yaml, js 等）を表示
 *   12. 全ページ検索       ... /search.json をロードして topbar 検索窓で絞り込み
 *   13. Mock demo 用       ... 検索・行クリック・新規追加・編集モード・トースト
 * ============================================================================ */

/* ---------- 定数 ---------- */
const TOAST_DISPLAY_MS = 1800;
const BACK_TO_TOP_THRESHOLD_PX = 300;

/* パンくず階層のラベル辞書。URL セグメント → 表示名。未登録は素通し。 */
const BREADCRUMB_LABELS = {
  "": "トップ",
  "docs": "ドキュメント",
  "mock": "モック",
  "wiki": "Wiki",
  "pages": "画面",
  "components": "コンポーネント",
  "styles": "スタイル",
  "issues": "Issue",
  "assets": "アセット",
  "gh-kit": "gh-kit",
  "テンプレート": "テンプレート",
  "規約": "規約",
};


/* ============================================================================
 * 1. パンくずリスト
 * ---------------------------------------------------------------------------- */

/** ルート（末尾スラッシュ付き）とパス配下のセグメントに分割する */
function splitPathBySiteRoot() {
  // _layouts/default.html が data-site-root="{{ '/' | relative_url }}" を注入する
  // GitHub Pages（project pages）だと "/my-plugins/"、ローカルルート配信だと "/"
  const bodyRoot = document.body?.dataset?.siteRoot || "/";
  const siteRoot = bodyRoot.endsWith("/") ? bodyRoot : bodyRoot + "/";

  const pathname = decodeURIComponent(window.location.pathname);
  // 末尾のファイル名を落として必ずディレクトリ形にする
  const dir = pathname.endsWith("/") ? pathname : pathname.replace(/\/[^\/]*$/, "/");

  // site root 直下の相対パスを取り出す
  const rel = dir.startsWith(siteRoot) ? dir.slice(siteRoot.length) : dir.replace(/^\//, "");
  const segs = rel.split("/").filter(Boolean);
  return { siteRoot, segs };
}

/** その中間層セグメントを「非リンクの中間表示」にするかどうか */
function isNonLinkableSegment(seg, index, segs) {
  // pages/{画面名}/issues/ は index.md を置かない中間層（規約）→ リンクにしない
  return seg === "issues" && segs[index - 2] === "pages";
}

/** URL パスの各セグメントを辿ってパンくずリンクを組み立てる */
function buildBreadcrumb() {
  const host = document.querySelector("[data-breadcrumb]");
  if (!host) return;

  const { siteRoot, segs } = splitPathBySiteRoot();

  const parts = [];
  parts.push(`<a href="${siteRoot}">${BREADCRUMB_LABELS[""]}</a>`);

  // 各セグメントの累積 URL を絶対パス（site root からの絶対）で組む
  let acc = siteRoot;
  segs.forEach((seg, i) => {
    acc += seg + "/";
    const label = BREADCRUMB_LABELS[seg] || seg;
    const isLast = i === segs.length - 1;
    parts.push(`<span class="sep">/</span>`);
    if (isLast || isNonLinkableSegment(seg, i, segs)) {
      // 現在地 or 中間層 → リンクにしない
      parts.push(`<span class="current">${label}</span>`);
    } else {
      parts.push(`<a href="${acc}">${label}</a>`);
    }
  });

  host.innerHTML = parts.join("");
}


/* ============================================================================
 * 2-3. テーブルソート・フィルタ
 * ---------------------------------------------------------------------------- */

/** 指定スコープ内のテーブルにソートとフィルタを付与する */
function enhanceTables(scope) {
  scope.querySelectorAll("table").forEach((table) => {
    // 二重適用防止
    if (table.dataset.enhanced === "true") return;
    table.dataset.enhanced = "true";
    bindTableSort(table);
    injectTableFilter(table);
  });
}

/** テーブルヘッダをクリックで昇降ソートできるようにする */
function bindTableSort(table) {
  const thead = table.tHead;
  const tbody = table.tBodies[0];
  if (!thead || !tbody) return;

  Array.from(thead.rows[0].cells).forEach((th, colIdx) => {
    th.classList.add("sortable");
    th.addEventListener("click", () => {
      // 現状の方向を判定して反転（初回は昇順）
      const asc = !th.classList.contains("sort-asc");
      // 他のヘッダの矢印はクリア
      Array.from(thead.rows[0].cells).forEach((h) => h.classList.remove("sort-asc", "sort-desc"));
      th.classList.add(asc ? "sort-asc" : "sort-desc");

      const rows = Array.from(tbody.rows);
      rows.sort((a, b) => compareCells(a.cells[colIdx], b.cells[colIdx], asc));
      rows.forEach((row) => tbody.appendChild(row));
    });
  });
}

/** セル内容を数値優先で比較する */
function compareCells(a, b, asc) {
  const av = (a?.textContent || "").trim();
  const bv = (b?.textContent || "").trim();
  const an = Number(av);
  const bn = Number(bv);
  let result;
  if (!Number.isNaN(an) && !Number.isNaN(bn) && av !== "" && bv !== "") {
    result = an - bn;
  } else {
    result = av.localeCompare(bv, "ja");
  }
  return asc ? result : -result;
}

/** テーブル上に検索ボックスを挿入し、入力語で行を絞り込む */
function injectTableFilter(table) {
  const tbody = table.tBodies[0];
  if (!tbody || tbody.rows.length < 2) return; // 行が少なければフィルタ不要

  const input = document.createElement("input");
  input.type = "search";
  input.className = "table-filter";
  input.placeholder = "この表を絞り込む...";
  table.parentNode.insertBefore(input, table);

  input.addEventListener("input", () => {
    const keyword = input.value.trim().toLowerCase();
    Array.from(tbody.rows).forEach((row) => {
      const text = row.textContent.toLowerCase();
      row.classList.toggle("hidden", keyword !== "" && !text.includes(keyword));
    });
  });
}


/* ============================================================================
 * 4. 見出しアンカーリンク
 * ---------------------------------------------------------------------------- */

/** 日本語見出しからも使えるスラッグを生成する */
function slugify(text) {
  return text
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    // URL で問題になる記号だけ落とす。日本語文字はそのまま残す（modern browser は decode 済で扱う）
    .replace(/[^\p{L}\p{N}\-_.]/gu, "");
}

/** h2〜h4 に id と # リンクを付与する */
function insertHeadingAnchors() {
  const root = document.querySelector(".markdown-body");
  if (!root) return;
  const used = new Set();

  root.querySelectorAll("h2, h3, h4").forEach((h) => {
    // id が既にあればそれを、無ければ本文から生成
    let id = h.id || slugify(h.textContent || "");
    if (!id) return;
    // 重複回避
    let unique = id;
    let n = 2;
    while (used.has(unique)) unique = `${id}-${n++}`;
    used.add(unique);
    h.id = unique;

    const a = document.createElement("a");
    a.className = "heading-anchor";
    a.href = `#${unique}`;
    a.setAttribute("aria-label", "この見出しへのリンクをコピー");
    a.textContent = "#";
    // クリック時に URL をクリップボードへコピー（ページ遷移はそのまま）
    a.addEventListener("click", () => {
      const url = window.location.origin + window.location.pathname + `#${unique}`;
      navigator.clipboard?.writeText(url).then(() => showToast(`URL をコピー: #${unique}`));
    });
    h.appendChild(a);
  });
}


/* ============================================================================
 * 5. コードブロックのコピーボタン
 * ---------------------------------------------------------------------------- */

/** `<pre><code>` の右上にコピーボタンを差し込む */
function addCodeCopyButtons() {
  document.querySelectorAll(".markdown-body pre").forEach((pre) => {
    if (pre.dataset.copyReady === "true") return;
    pre.dataset.copyReady = "true";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "code-copy";
    btn.textContent = "コピー";
    btn.addEventListener("click", async () => {
      const code = pre.querySelector("code")?.innerText ?? pre.innerText;
      try {
        await navigator.clipboard.writeText(code);
        btn.textContent = "コピー済";
        window.setTimeout(() => { btn.textContent = "コピー"; }, 1500);
      } catch {
        btn.textContent = "失敗";
      }
    });
    // pre を position: relative にして右上に置く
    pre.style.position = "relative";
    pre.appendChild(btn);
  });
}


/* ============================================================================
 * 6. MD ダウンロード（raw リンク）
 * ---------------------------------------------------------------------------- */

/** [data-md-download] を現在ページに対応する raw MD の URL に張り替える */
function bindMdDownloadLink() {
  const link = document.querySelector("[data-md-download]");
  if (!link) return;
  const rawBase = document.body?.dataset?.rawBase;
  const pagePath = document.body?.dataset?.pagePath;
  if (!rawBase || !pagePath) {
    link.hidden = true;
    return;
  }
  // rawBase 末尾のスラッシュ調整
  const base = rawBase.replace(/\/+$/, "");
  // pagePath は Jekyll が Liquid で埋めた実ソースパス（例: "mock/index.md" / "wiki/gh-kit/規約/Wiki管理.md"）
  link.href = `${base}/${pagePath}`;
  link.target = "_blank";
  link.rel = "noopener";
}


/* ============================================================================
 * 8. 目次サイドバー
 * ---------------------------------------------------------------------------- */

/** .markdown-body の h2/h3 から目次を組み立て、スクロールで現在位置をハイライト */
function buildToc() {
  const container = document.querySelector("[data-toc]");
  const list = document.querySelector("[data-toc-list]");
  const root = document.querySelector(".markdown-body");
  if (!container || !list || !root) return;

  const headings = Array.from(root.querySelectorAll("h2, h3"));
  if (headings.length < 2) {
    // 見出し 1 個以下では目次不要
    return;
  }
  container.hidden = false;

  headings.forEach((h) => {
    if (!h.id) return;
    const li = document.createElement("li");
    li.className = h.tagName === "H3" ? "toc-item toc-lv3" : "toc-item toc-lv2";
    const a = document.createElement("a");
    a.href = `#${h.id}`;
    // アンカー "#" は本文だけ取り出す
    a.textContent = h.textContent.replace(/#$/, "").trim();
    li.appendChild(a);
    list.appendChild(li);
  });

  // スクロール位置に応じた「常に 1 つだけ active」ハイライト
  // topbar 高さ + 少しの余白より上に位置する見出しのうち最後尾を active にする
  const links = Array.from(list.querySelectorAll("a"));
  const linkById = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));

  const updateActive = () => {
    const topbarH = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--topbar-h")) || 56;
    const spaceMd = 16;
    const threshold = topbarH + spaceMd + 4; // トップバー直下より下に降りた見出しを現在地とみなす

    let currentId = null;
    for (const h of headings) {
      if (!h.id) continue;
      const rect = h.getBoundingClientRect();
      if (rect.top <= threshold) {
        currentId = h.id;
      } else {
        break; // 見出しは DOM 順に並ぶので、閾値より下に来た時点で以降を見る必要なし
      }
    }
    // 全リンクの active をクリアしてから 1 つだけ付ける
    links.forEach((a) => a.classList.remove("active"));
    if (currentId) {
      const a = linkById.get(currentId);
      if (a) a.classList.add("active");
    }
  };

  window.addEventListener("scroll", updateActive, { passive: true });
  window.addEventListener("resize", updateActive);
  updateActive();
}


/* ============================================================================
 * 9. ダークモード切替
 * ---------------------------------------------------------------------------- */

const THEME_STORAGE_KEY = "docs-theme";

/** 現在のテーマを html[data-theme] に反映 */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  // Mermaid にも反映（再描画）
  if (window.mermaid && typeof window.mermaid.initialize === "function") {
    window.mermaid.initialize({ startOnLoad: false, theme: theme === "dark" ? "dark" : "default" });
  }
}

/** ボタン + localStorage + OS 設定でテーマを決める */
function bindThemeToggle() {
  const btn = document.querySelector("[data-theme-toggle]");
  // OS 設定 → localStorage の順で初期値
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initial = stored || (prefersDark ? "dark" : "light");
  applyTheme(initial);
  if (!btn) return;

  btn.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem(THEME_STORAGE_KEY, next);
    // 既存の mermaid をテーマ変更後に再描画（グラフを破棄して再生成）
    rerenderMermaid();
  });
}


/* ============================================================================
 * 10. Mermaid 自動描画
 * ---------------------------------------------------------------------------- */

/** 元 MD テキストを data 属性に退避して SVG に置き換える */
async function renderMermaid() {
  if (!window.mermaid) return;
  const blocks = document.querySelectorAll("pre > code.language-mermaid");
  if (blocks.length === 0) return;

  window.mermaid.initialize({ startOnLoad: false, theme: document.documentElement.dataset.theme === "dark" ? "dark" : "default" });

  for (const [i, code] of blocks.entries()) {
    const pre = code.parentElement;
    const src = code.textContent;
    // pre 全体を div.mermaid に置き換える（元テキストは data-mermaid-src に退避）
    const holder = document.createElement("div");
    holder.className = "mermaid-holder";
    holder.dataset.mermaidSrc = src;
    try {
      const id = `mermaid-${Date.now()}-${i}`;
      const { svg } = await window.mermaid.render(id, src);
      holder.innerHTML = svg;
    } catch (e) {
      holder.innerHTML = `<div class="md-error">Mermaid の描画に失敗: ${e?.message ?? e}</div>`;
    }
    pre.replaceWith(holder);
  }
}

/** テーマ切替時に既存の Mermaid ホルダーを再描画する */
async function rerenderMermaid() {
  if (!window.mermaid) return;
  const holders = document.querySelectorAll(".mermaid-holder[data-mermaid-src]");
  window.mermaid.initialize({ startOnLoad: false, theme: document.documentElement.dataset.theme === "dark" ? "dark" : "default" });
  for (const [i, holder] of holders.entries()) {
    const src = holder.dataset.mermaidSrc;
    try {
      const id = `mermaid-re-${Date.now()}-${i}`;
      const { svg } = await window.mermaid.render(id, src);
      holder.innerHTML = svg;
    } catch (e) {
      holder.innerHTML = `<div class="md-error">Mermaid の描画に失敗: ${e?.message ?? e}</div>`;
    }
  }
}


/* ============================================================================
 * 11. コードブロックの言語ラベル
 * ---------------------------------------------------------------------------- */

/** code の class="language-xxx" から言語名を取り出して pre 左上に付ける */
function addCodeLangLabels() {
  document.querySelectorAll(".markdown-body pre > code[class*='language-']").forEach((code) => {
    const pre = code.parentElement;
    if (pre.dataset.langReady === "true") return;
    pre.dataset.langReady = "true";

    const m = /language-([^\s]+)/.exec(code.className);
    if (!m) return;
    const lang = m[1];
    // mermaid はラベル不要（図として表示するので）
    if (lang === "mermaid") return;

    const label = document.createElement("span");
    label.className = "code-lang";
    label.textContent = lang;
    pre.style.position = "relative";
    pre.appendChild(label);
  });
}


/* ============================================================================
 * 12. 全ページ検索
 * ---------------------------------------------------------------------------- */

let searchIndexCache = null;

/** search.json を初回だけ fetch する */
async function loadSearchIndex() {
  if (searchIndexCache) return searchIndexCache;
  const url = document.body?.dataset?.searchIndex;
  if (!url) return [];
  const res = await fetch(url);
  if (!res.ok) return [];
  searchIndexCache = await res.json();
  return searchIndexCache;
}

/** クエリで entries を絞り込む（title / url / path / content 部分一致） */
function filterSearch(entries, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return entries
    .map((e) => {
      const hay = `${e.title}\n${e.url}\n${e.path}\n${e.content}`.toLowerCase();
      const idx = hay.indexOf(q);
      if (idx < 0) return null;
      // タイトル一致を最上位、次に path、最後に本文
      const score =
        (e.title?.toLowerCase().includes(q) ? 0 : 100) +
        (e.path?.toLowerCase().includes(q) ? 0 : 50) +
        idx / 1000;
      return { entry: e, score };
    })
    .filter(Boolean)
    .sort((a, b) => a.score - b.score)
    .slice(0, 10)
    .map((x) => x.entry);
}

/** topbar 検索入力にドロップダウン結果を紐付ける */
function bindSearchBox() {
  const input = document.querySelector("[data-search-input]");
  const results = document.querySelector("[data-search-results]");
  if (!input || !results) return;

  const render = (entries) => {
    if (entries.length === 0) {
      results.hidden = true;
      results.innerHTML = "";
      return;
    }
    results.hidden = false;
    results.innerHTML = entries
      .map((e) => `
        <li>
          <a href="${e.url}">
            <span class="search-title">${escapeHtml(e.title)}</span>
            <span class="search-path">${escapeHtml(e.path)}</span>
          </a>
        </li>
      `)
      .join("");
  };

  const handle = async () => {
    const entries = await loadSearchIndex();
    render(filterSearch(entries, input.value));
  };
  input.addEventListener("input", handle);
  input.addEventListener("focus", handle);
  // ドロップダウン外をクリックしたら閉じる
  document.addEventListener("click", (e) => {
    if (!results.contains(e.target) && e.target !== input) {
      results.hidden = true;
    }
  });
}

/** HTML エスケープ（検索結果の描画に使う） */
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}


/* ============================================================================
 * 7. トップに戻るボタン
 * ---------------------------------------------------------------------------- */

/** スクロール量で表示切替し、クリックで先頭へスムーズスクロール */
function bindBackToTop() {
  const btn = document.querySelector("[data-back-to-top]");
  if (!btn) return;

  const update = () => {
    btn.classList.toggle("visible", window.scrollY > BACK_TO_TOP_THRESHOLD_PX);
  };
  window.addEventListener("scroll", update, { passive: true });
  update();

  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}


/* ============================================================================
 * 8. Mock demo 用ハンドラ
 * 対象 DOM が無いページでは何もしない（早期 return）。
 * ---------------------------------------------------------------------------- */

/** 検索ボックスの入力語で顧客一覧の行を絞り込む */
function bindSearchFilter() {
  const input = document.getElementById("search");
  if (!input) return;
  input.addEventListener("input", () => {
    const keyword = input.value.trim().toLowerCase();
    document.querySelectorAll("#customer-table tbody tr").forEach((row) => {
      const text = row.textContent.toLowerCase();
      row.classList.toggle("hidden", keyword !== "" && !text.includes(keyword));
    });
  });
}

/** 行クリックで疑似遷移トーストを表示する */
function bindRowClick() {
  document.querySelectorAll("#customer-table tbody tr").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target instanceof HTMLInputElement) return;
      const id = row.dataset.id;
      showToast(`顧客 ${id} を選択しました（モック）`);
    });
  });
}

/** 新規追加ボタンでトーストを一時表示する */
function bindNewButton() {
  const button = document.getElementById("new-btn");
  if (!button) return;
  button.addEventListener("click", () => {
    showToast("新規追加ダイアログを開きました（モック）");
  });
}

/** 詳細画面の編集モードを切り替える */
function bindEditMode() {
  const editBtn = document.getElementById("edit-btn");
  const cancelBtn = document.getElementById("cancel-btn");
  const saveBtn = document.getElementById("save-btn");
  if (!editBtn || !cancelBtn || !saveBtn) return;

  /** 編集可能フィールドの readonly 属性を切り替える */
  function setEditing(editing) {
    document.querySelectorAll(".field-value input, .field-value textarea").forEach((field) => {
      if (editing) field.removeAttribute("readonly");
      else field.setAttribute("readonly", "readonly");
    });
    editBtn.hidden = editing;
    cancelBtn.hidden = !editing;
    saveBtn.hidden = !editing;
  }

  editBtn.addEventListener("click", () => setEditing(true));
  cancelBtn.addEventListener("click", () => setEditing(false));
  saveBtn.addEventListener("click", () => {
    setEditing(false);
    showToast("変更を保存しました（モック）");
  });
}

/** 画面下部のトーストを一定時間表示する */
function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => {
    toast.hidden = true;
  }, TOAST_DISPLAY_MS);
}


/* ============================================================================
 * エントリポイント
 * ---------------------------------------------------------------------------- */

/** Mock demo 画面用にトースト要素が無ければ差し込む（他画面の共通機能でも使うため） */
function ensureToastElement() {
  if (document.getElementById("toast")) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.id = "toast";
  t.hidden = true;
  document.body.appendChild(t);
}

async function init() {
  // 共通機能
  ensureToastElement();
  bindThemeToggle();                 // 最初にテーマを反映（フラッシュ抑止）
  buildBreadcrumb();
  bindBackToTop();
  bindMdDownloadLink();
  insertHeadingAnchors();            // まず見出しに id を振る（TOC がそれを使う）
  buildToc();
  addCodeLangLabels();
  addCodeCopyButtons();
  await renderMermaid();              // mermaid は pre を差し替えるので copy/label より後
  enhanceTables(document);
  bindSearchBox();

  // Mock demo 固有のハンドラ
  bindSearchFilter();
  bindRowClick();
  bindNewButton();
  bindEditMode();
}

document.addEventListener("DOMContentLoaded", init);
