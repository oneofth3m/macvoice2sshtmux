from voice2tmux.command_parser import CommandParser, CommandType


def test_new_line_command() -> None:
    parser = CommandParser()
    result = parser.parse("new line")
    assert result.command == CommandType.NEW_LINE
    assert result.text == "\n"


def test_regular_text_passthrough() -> None:
    parser = CommandParser()
    result = parser.parse("build me a script")
    assert result.command == CommandType.NONE
    assert result.text == "build me a script"

