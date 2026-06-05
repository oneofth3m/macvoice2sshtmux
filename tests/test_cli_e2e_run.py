from __future__ import annotations

def test_run_with_explicit_target_streams_text(runner, patched_main) -> None:
    result = runner.invoke(
        patched_main.app,
        ["run", "--ssh-host", "devbox", "--tmux-target", "%9", "--once"],
        input="hello world\n",
    )

    assert result.exit_code == 0
    assert patched_main.TmuxTargetResolver.resolved_specs == ["%9"]
    assert len(patched_main.TmuxWriter.calls) == 1
    assert patched_main.TmuxWriter.calls[0].pane_id == "%9"
    assert patched_main.TmuxWriter.calls[0].append_text == "hello world"
    assert "voice2tmux started" in result.stdout
    assert "voice2tmux stopped." in result.stdout


def test_run_without_target_uses_interactive_selector(runner, patched_main) -> None:
    result = runner.invoke(
        patched_main.app,
        ["run", "--ssh-host", "devbox", "--once"],
        input="1\n1\n1\nhello from selector\n",
    )

    assert result.exit_code == 0
    assert patched_main.TmuxTargetResolver.resolved_specs == ["%1"]
    assert len(patched_main.TmuxWriter.calls) == 1
    assert patched_main.TmuxWriter.calls[0].pane_id == "%1"
    assert patched_main.TmuxWriter.calls[0].append_text == "hello from selector"
    assert "Select tmux session" in result.stdout
    assert "Select tmux window" in result.stdout
    assert "Select tmux pane" in result.stdout


def test_run_handles_commands_in_flow(runner, patched_main) -> None:
    result = runner.invoke(
        patched_main.app,
        ["run", "--ssh-host", "devbox", "--tmux-target", "%5"],
        input="hello world\nscratch that\nnew line\ncancel\n",
    )

    assert result.exit_code == 0
    assert [call.append_text for call in patched_main.TmuxWriter.calls] == [
        "hello world",
        "",
        "\n",
    ]
    assert [call.delete_count for call in patched_main.TmuxWriter.calls] == [0, 6, 0]


def test_run_inserts_space_across_transcript_chunks(runner, patched_main) -> None:
    result = runner.invoke(
        patched_main.app,
        ["run", "--ssh-host", "devbox", "--tmux-target", "%8"],
        input="Hello\nWhat\ncancel\n",
    )

    assert result.exit_code == 0
    assert [call.append_text for call in patched_main.TmuxWriter.calls] == [
        "Hello",
        " What",
    ]


def test_run_dedupes_immediate_duplicate_chunks(runner, patched_main) -> None:
    result = runner.invoke(
        patched_main.app,
        ["run", "--ssh-host", "devbox", "--tmux-target", "%8"],
        input="Excellent\nExcellent\ncancel\n",
    )

    assert result.exit_code == 0
    assert [call.append_text for call in patched_main.TmuxWriter.calls] == ["Excellent"]


def test_run_accepts_punctuated_command_variants(runner, patched_main) -> None:
    result = runner.invoke(
        patched_main.app,
        ["run", "--ssh-host", "devbox", "--tmux-target", "%8"],
        input="Hello\nnew line please.\ncancel.\n",
    )

    assert result.exit_code == 0
    assert [call.append_text for call in patched_main.TmuxWriter.calls] == ["Hello", "\n"]
