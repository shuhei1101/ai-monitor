"""セッション台帳。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_monitor.features.sessions.state_store import load_sessions, save_sessions
from ai_monitor.features.sessions.types import AgentSession


class SessionRegistry:
    """起動中エージェントセッション一覧の台帳。"""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self.sessions: list[AgentSession] = load_sessions(state_path)

    def find(self, project: str, agent_name: str, number: int) -> AgentSession | None:
        """プロジェクト + エージェント名 + 番号でセッションを検索する。"""
        for session in self.sessions:
            if session.project != project or session.agent_name != agent_name:
                continue
            # 主番号または監視面番号一覧との一致で解決する
            if session.primary_number == number or number in session.watch_numbers:
                return session
        return None

    def register(self, session: AgentSession) -> None:
        """セッションを追加して永続化する。"""
        self.sessions.append(session)
        save_sessions(self._state_path, self.sessions)

    def touch(self, session_name: str) -> None:
        """`last_seen_at` を現在時刻に更新する。"""
        for session in self.sessions:
            if session.session_name == session_name:
                session.last_seen_at = datetime.now(timezone.utc).astimezone().isoformat()
        save_sessions(self._state_path, self.sessions)

    def add_watch(self, project: str, agent_name: str, primary_number: int, numbers: list[int]) -> None:
        """監視面番号一覧に番号を追加して永続化する。"""
        session = self._find_by_primary(project, agent_name, primary_number)
        # 未登録の番号だけを追加する（登録済みは無視する冪等操作）
        for number in numbers:
            if number not in session.watch_numbers:
                session.watch_numbers.append(number)
        save_sessions(self._state_path, self.sessions)

    def remove_watch(self, project: str, agent_name: str, primary_number: int, numbers: list[int]) -> None:
        """監視面番号一覧から番号を取り除いて永続化する。"""
        session = self._find_by_primary(project, agent_name, primary_number)
        # 未登録の番号は無視する冪等操作
        session.watch_numbers = [n for n in session.watch_numbers if n not in numbers]
        save_sessions(self._state_path, self.sessions)

    def remove(self, session_name: str) -> None:
        """セッションを 1 件だけ台帳から除去して永続化する。"""
        # 該当なしは無視する冪等操作
        self.sessions = [s for s in self.sessions if s.session_name != session_name]
        save_sessions(self._state_path, self.sessions)

    def release_by_number(self, project: str, number: int) -> list[AgentSession]:
        """プロジェクトと主番号が一致する全セッションを除去して返す。"""
        released = [s for s in self.sessions if s.project == project and s.primary_number == number]
        self.sessions = [s for s in self.sessions if s not in released]
        save_sessions(self._state_path, self.sessions)
        return released

    def _find_by_primary(self, project: str, agent_name: str, primary_number: int) -> AgentSession:
        for session in self.sessions:
            if (
                session.project == project
                and session.agent_name == agent_name
                and session.primary_number == primary_number
            ):
                return session
        raise KeyError(f"{project}/{agent_name}/{primary_number}")
