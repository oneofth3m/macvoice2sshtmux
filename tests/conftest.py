from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pytest
from typer.testing import CliRunner

from voice2tmux.ipc_server import ControlEvent, IPCMessage
from voice2tmux.ssh_mux import SSHConfig
from voice2tmux.tmux_target import TmuxPane, TmuxSession, TmuxTarget, TmuxWindow


class FakeSSHMux:
    instances: list["FakeSSHMux"] = []

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self.commands: list[str] = []
        self.master_started = False
        self.__class__.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []

    def ensure_master(self) -> None:
        self.master_started = True

    def run(self, remote_command: str) -> str:
        self.commands.append(remote_command)
        return ""


class FakeTmuxTargetResolver:
    sessions: list[TmuxSession] = [TmuxSession(name="dev")]
    windows: list[TmuxWindow] = [TmuxWindow(index="1", name="editor")]
    panes: list[TmuxPane] = [
        TmuxPane(index="0", pane_id="%1", current_command="bash", is_active=True)
    ]
    resolved_specs: list[str] = []

    def __init__(self, ssh: FakeSSHMux) -> None:
        self.ssh = ssh

    @classmethod
    def reset(cls) -> None:
        cls.sessions = [TmuxSession(name="dev")]
        cls.windows = [TmuxWindow(index="1", name="editor")]
        cls.panes = [TmuxPane(index="0", pane_id="%1", current_command="bash", is_active=True)]
        cls.resolved_specs = []

    def current_active_target(self) -> TmuxTarget:
        return TmuxTarget(session_id="$0", window_id="@1", pane_id="%1")

    def list_sessions(self) -> list[TmuxSession]:
        return list(self.sessions)

    def list_windows(self, session_name: str) -> list[TmuxWindow]:
        return list(self.windows)

    def list_panes(self, target_window: str) -> list[TmuxPane]:
        return list(self.panes)

    def resolve_target(self, target_spec: str) -> TmuxTarget:
        self.__class__.resolved_specs.append(target_spec)
        return TmuxTarget(session_id="$0", window_id="@1", pane_id=target_spec)


@dataclass
class WriterCall:
    pane_id: str
    delete_count: int
    append_text: str


class FakeTmuxWriter:
    calls: list[WriterCall] = []
    fail_next_calls: int = 0

    def __init__(self, ssh: FakeSSHMux) -> None:
        self.ssh = ssh

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.fail_next_calls = 0

    def apply_tail_patch(self, target: TmuxTarget, patch) -> None:
        if self.__class__.fail_next_calls > 0:
            self.__class__.fail_next_calls -= 1
            raise RuntimeError("simulated write failure")
        self.__class__.calls.append(
            WriterCall(
                pane_id=target.pane_id,
                delete_count=patch.delete_count,
                append_text=patch.append_text,
            )
        )


class FakeIPCServer:
    scripted_batches: list[list[ControlEvent]] = []
    created: list["FakeIPCServer"] = []

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self.started = False
        self.stopped = False
        self.__class__.created.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.scripted_batches = []
        cls.created = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def pop_all(self) -> List[IPCMessage]:
        if not self.__class__.scripted_batches:
            return []
        batch = self.__class__.scripted_batches.pop(0)
        return [IPCMessage(event=e) for e in batch]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def patched_main(monkeypatch):
    import voice2tmux.main as main

    FakeSSHMux.reset()
    FakeTmuxTargetResolver.reset()
    FakeTmuxWriter.reset()
    FakeIPCServer.reset()

    monkeypatch.setattr(main, "SSHMux", FakeSSHMux)
    monkeypatch.setattr(main, "TmuxTargetResolver", FakeTmuxTargetResolver)
    monkeypatch.setattr(main, "TmuxWriter", FakeTmuxWriter)
    monkeypatch.setattr(main, "IPCServer", FakeIPCServer)
    return main
