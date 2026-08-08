"""Milestone クエリ 1 回分の応答から、PR の集合と base による親子復元を検証する。"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    """標準入力の GraphQL 応答を読み、集合と親子の復元結果を出力する。"""
    data = json.load(sys.stdin)
    milestone = data["data"]["repository"]["issue"]["milestone"]
    prs = milestone["pullRequests"]["nodes"]
    issues = milestone["issues"]["nodes"]

    cost = data["data"]["rateLimit"]["cost"]
    print(f"cost={cost} milestone={milestone['number']}")
    print(f"issues={[i['number'] for i in issues]}")
    print(f"prs={[p['number'] for p in prs]}")

    # head ブランチ名 → PR 番号。子 PR の base は親 PR の head なのでこれで引ける
    by_head = {p["headRefName"]: p["number"] for p in prs}
    parent = {p["number"]: by_head.get(p["baseRefName"]) for p in prs}

    print("\n== 同じ応答から親子を復元 ==")
    for pr in prs:
        got = parent[pr["number"]] or "なし（レイヤー最上位）"
        print(f"PR #{pr['number']} ({pr['title']})  base={pr['baseRefName']}  -> 親 = {got}")

    print("\n== 期待との突き合わせ ==")
    epic, story, work, poc = (
        int(os.environ[k]) for k in ("PR_EPIC", "PR_STORY", "PR_WORK", "PR_POC")
    )
    expected = ((story, epic), (work, story), (poc, epic), (epic, None))
    ng = 0
    for pr_number, want in expected:
        got = parent.get(pr_number)
        ok = got == want
        ng += 0 if ok else 1
        print(f"#{pr_number}: 期待={want or 'なし'} 実測={got or 'なし'} {'OK' if ok else 'NG'}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
