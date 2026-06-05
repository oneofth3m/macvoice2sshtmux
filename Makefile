PYTHON ?= python3
PYTHON_VERSION ?= 3.11.9
PROJECT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

.PHONY: setup run serve event test lint clean

setup:
	@if command -v pyenv >/dev/null 2>&1; then \
		echo "Using pyenv ($(PYTHON_VERSION)) for local project interpreter"; \
		pyenv install -s $(PYTHON_VERSION); \
		pyenv local $(PYTHON_VERSION); \
		PYTHON_BIN="$$(pyenv which python)"; \
	else \
		echo "pyenv not found; using system python to create isolated .venv"; \
		PYTHON_BIN="$$(command -v $(PYTHON))"; \
	fi; \
	test -n "$$PYTHON_BIN" || (echo "Python not found on PATH" && exit 1); \
	cd "$(PROJECT_DIR)" && "$$PYTHON_BIN" -m venv $(VENV)
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && python -m pip install --upgrade pip
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && pip install -e ".[dev,asr]"

run:
	@test -n "$(SSH_HOST)" || (echo "Usage: make run SSH_HOST=<your_ssh_alias> [TMUX_TARGET=<%pane_or_session:window.pane>]" && exit 1)
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && if [ -n "$(TMUX_TARGET)" ]; then \
		voice2tmux run --ssh-host $(SSH_HOST) --tmux-target $(TMUX_TARGET); \
	else \
		voice2tmux run --ssh-host $(SSH_HOST); \
	fi

serve:
	@test -n "$(SSH_HOST)" || (echo "Usage: make serve SSH_HOST=<your_ssh_alias> [TMUX_TARGET=<%pane_or_session:window.pane>]" && exit 1)
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && if [ -n "$(TMUX_TARGET)" ]; then \
		voice2tmux serve --ssh-host $(SSH_HOST) --tmux-target $(TMUX_TARGET); \
	else \
		voice2tmux serve --ssh-host $(SSH_HOST); \
	fi

event:
	@test -n "$(EVENT)" || (echo "Usage: make event EVENT=start|stop|confirm|cancel" && exit 1)
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && voice2tmux event --event $(EVENT)

test:
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && pytest -q

lint:
	@cd "$(PROJECT_DIR)" && $(ACTIVATE) && ruff check src tests

clean:
	@cd "$(PROJECT_DIR)" && rm -rf $(VENV) .pytest_cache .ruff_cache
