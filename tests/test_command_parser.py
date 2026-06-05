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


def test_tolerates_command_punctuation_variants() -> None:
    parser = CommandParser()
    assert parser.parse("scratch that.").command == CommandType.SCRATCH_THAT
    assert parser.parse("new line!").command == CommandType.NEW_LINE


def test_tolerates_polite_command_variants() -> None:
    parser = CommandParser()
    assert parser.parse("new paragraph please").command == CommandType.NEW_PARAGRAPH
    assert parser.parse("cancel, please").command == CommandType.CANCEL

