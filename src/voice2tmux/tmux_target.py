from __future__ import annotations

import shlex
from dataclasses import dataclass

from .ssh_mux import SSHMux


@dataclass(frozen=True)
class TmuxSession:
    name: str


@dataclass(frozen=True)
class TmuxWindow:
    index: str
    name: str


@dataclass(frozen=True)
class TmuxPane:
    index: str
    pane_id: str
    current_command: str
    is_active: bool


@dataclass(frozen=True)
class TmuxTarget:
    session_id: str
    window_id: str
    pane_id: str


class TmuxTargetResolver:
    def __init__(self, ssh: SSHMux) -> None:
        self.ssh = ssh

    def current_active_target(self) -> TmuxTarget:
        output = self.ssh.run(
            "tmux display-message -p -F '#{session_id} #{window_id} #{pane_id}'"
        )
        session_id, window_id, pane_id = output.split()
        return TmuxTarget(session_id=session_id, window_id=window_id, pane_id=pane_id)

    def list_sessions(self) -> list[TmuxSession]:
        output = self.ssh.run("tmux list-sessions -F '#{session_name}'")
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return [TmuxSession(name=name) for name in lines]

    def list_windows(self, session_name: str) -> list[TmuxWindow]:
        output = self.ssh.run(
            f"tmux list-windows -t {shlex.quote(session_name)} -F '#{{window_index}}\t#{{window_name}}'"
        )
        windows: list[TmuxWindow] = []
        for line in output.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                windows.append(TmuxWindow(index=parts[0], name=parts[1]))
        return windows

    def list_panes(self, target_window: str) -> list[TmuxPane]:
        output = self.ssh.run(
            f"tmux list-panes -t {shlex.quote(target_window)} -F '#{{pane_index}}\t#{{pane_id}}\t#{{pane_current_command}}\t#{{?pane_active,1,0}}'"
        )
        panes: list[TmuxPane] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                panes.append(
                    TmuxPane(
                        index=parts[0],
                        pane_id=parts[1],
                        current_command=parts[2],
                        is_active=parts[3] == "1",
                    )
                )
        return panes

    def resolve_target(self, target_spec: str) -> TmuxTarget:
        """
        Resolves a deterministic tmux target.

        Supported values:
        - "active" (legacy behavior)
        - pane id (e.g. "%12")
        - tmux target forms accepted by -t (e.g. "session:window.pane")
        """
        if target_spec == "active":
            return self.current_active_target()
        output = self.ssh.run(
            f"tmux display-message -p -t {shlex.quote(target_spec)} -F '#{{session_id}} #{{window_id}} #{{pane_id}}'"
        )
        session_id, window_id, pane_id = output.split()
        return TmuxTarget(session_id=session_id, window_id=window_id, pane_id=pane_id)

