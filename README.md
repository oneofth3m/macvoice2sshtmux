# macvoice2sshtmux

Hotkey-driven near real-time voice prompt streaming from macOS into a remote Linux `tmux` pane over SSH.

> [!IMPORTANT]
> **Human vision, AI execution.** The owner designed the system; AI helped build the code. Review before production.

## Current status

This is an MVP scaffold focused on:

- rewrite-tail transcript model (`localDraft` vs `remoteEmitted`)
- SSH mux + tmux write primitives
- pane lock at capture start
- retry window handling for SSH drop (15 seconds)
- command parser for `new line`, `new paragraph`, `scratch that`, `cancel`
- local UNIX socket control (`start`, `stop`, `confirm`, `cancel`) for hotkey integration

Mic capture and live ASR adapter are pluggable and intentionally isolated.

## Step-by-step install and run

1) **Clone and enter the repo**

```bash
git clone https://github.com/oneofth3m/macvoice2sshtmux.git
cd macvoice2sshtmux
```

2) **Set local Python (pyenv preferred, fallback supported)**

```bash
make setup
```

`make setup` behavior:
- If `pyenv` exists, it pins local Python to `3.11.9` for this repo.
- If `pyenv` is not installed, it still creates a project-local `.venv` with system Python.
- In both paths, dependencies are installed only inside `.venv` (no global pip pollution).

3) **Activate the virtual environment**

```bash
source .venv/bin/activate
```

4) **Verify SSH + tmux prerequisites**

```bash
ssh <your_ssh_alias> "tmux -V && tmux list-sessions"
```

This must work without password prompts during normal use.

5) **Run the app (validation mode)**

```bash
make run SSH_HOST=<your_ssh_alias>
```

6) **Try a quick simulation**

- Type normal text and press Enter -> it is streamed to the locked remote tmux pane.
- Type `new line` -> inserts newline.
- Type `scratch that` -> removes last phrase from local draft and reconciles tail.
- Press `Ctrl-D` to stop.

No global `pip install` is required; all dependencies stay inside `./.venv`.

## Service mode (for hotkeys)

Run long-lived service:

```bash
make serve SSH_HOST=<your_ssh_alias>
```

From another terminal, trigger control events:

```bash
source .venv/bin/activate
voice2tmux event --event start
voice2tmux event --event stop
voice2tmux event --event confirm
voice2tmux event --event cancel
```

## Shortcut commands

```bash
make setup
make run SSH_HOST=<your_ssh_alias>
make serve SSH_HOST=<your_ssh_alias>
make event EVENT=start
make test
make lint
```

## Test and lint

```bash
source .venv/bin/activate
pytest -q
ruff check src tests
```

## Project structure

- `src/voice2tmux/command_parser.py`: direct command parsing
- `src/voice2tmux/transcript_buffer.py`: rewrite-tail diff model
- `src/voice2tmux/tmux_target.py`: active pane resolution
- `src/voice2tmux/tmux_writer.py`: tail patch application in tmux
- `src/voice2tmux/stream_controller.py`: retry and stream state handling
- `config.example.yaml`: tunable runtime defaults
- `tests/`: parser and transcript buffer tests

## Next implementation steps

1. Add streaming microphone capture in `audio_capture.py`.
2. Integrate faster-whisper partial hypotheses in `asr_engine.py`.
3. Add local IPC socket and Hammerspoon bindings.
4. Add launchd service + GitHub Actions CI.
