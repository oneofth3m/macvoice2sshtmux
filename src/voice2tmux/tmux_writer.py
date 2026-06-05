from __future__ import annotations

import shlex

from .ssh_mux import SSHMux
from .tmux_target import TmuxTarget
from .transcript_buffer import TailPatch


class TmuxWriter:
    def __init__(self, ssh: SSHMux) -> None:
        self.ssh = ssh

    def apply_tail_patch(self, target: TmuxTarget, patch: TailPatch) -> None:
        # Backspace tail chars, then paste append text via tmux buffer.
        if patch.delete_count > 0:
            delete_cmd = (
                f"for i in $(seq 1 {patch.delete_count}); do tmux send-keys -t {shlex.quote(target.pane_id)} C-h; done"
            )
            self.ssh.run(delete_cmd)
        if patch.append_text:
            escaped = shlex.quote(patch.append_text)
            cmd = (
                f"printf %s {escaped} | tmux load-buffer - && "
                f"tmux paste-buffer -t {shlex.quote(target.pane_id)} -d"
            )
            self.ssh.run(cmd)

