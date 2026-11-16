from commands.command_processor import CommandProcessor


def test_pipe_delimited_change_commands_are_parsed():
    commands = CommandProcessor._parse_commands(
        "1|POSTPONE|CSE101|2026-12-01|FN\n"
        "2|HALL_UNAVAILABLE|H01|2026-12-02|ALL\n"
    )

    assert commands == [
        {
            "sequence": "1",
            "command": "POSTPONE",
            "target": "CSE101",
            "parameter": "2026-12-01|FN",
        },
        {
            "sequence": "2",
            "command": "HALL_UNAVAILABLE",
            "target": "H01",
            "parameter": "2026-12-02|ALL",
        },
    ]


def test_whitespace_commands_can_omit_sequence():
    commands = CommandProcessor._parse_commands(
        "POSTPONE CSE101 2026-12-01 FN"
    )

    assert commands == [{
        "sequence": "1",
        "command": "POSTPONE",
        "target": "CSE101",
        "parameter": "2026-12-01|FN",
    }]
