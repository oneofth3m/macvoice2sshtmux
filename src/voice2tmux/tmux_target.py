from __future__ import annotations

from dataclasses import dataclass

from .ssh_mux import SSHMux


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

