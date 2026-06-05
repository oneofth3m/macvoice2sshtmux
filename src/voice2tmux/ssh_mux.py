from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SSHConfig:
    host_alias: str
    control_path: str = "~/.ssh/cm-%r@%h:%p"
    control_persist: str = "60s"


class SSHMux:
    def __init__(self, config: SSHConfig) -> None:
        self.config = config

    def _base_cmd(self) -> list[str]:
        return [
            "ssh",
            "-S",
            self.config.control_path,
            self.config.host_alias,
        ]

    def ensure_master(self) -> None:
        cmd = [
            "ssh",
            "-M",
            "-S",
            self.config.control_path,
            "-o",
            f"ControlPersist={self.config.control_persist}",
            "-fnN",
            self.config.host_alias,
        ]
        subprocess.run(cmd, check=False)

    def run(self, remote_command: str) -> str:
        cmd = self._base_cmd() + [remote_command]
        output = subprocess.check_output(cmd, text=True)
        return output.strip()

