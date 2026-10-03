import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input.voice import parse_command, VoiceParserError, InputCommand


def test_valid_commands():
    test_cases = [
        # Primary grammar: "switch on/off"
        ("switch on light", InputCommand("light", "on", None)),
        ("switch off light", InputCommand("light", "off", None)),
        ("switch on fan", InputCommand("fan", "on", None)),
        ("switch off fan", InputCommand("fan", "off", None)),
        ("switch on tv", InputCommand("tv", "on", None)),
        ("switch off tv", InputCommand("tv", "off", None)),
        ("switch on ac", InputCommand("ac", "on", None)),
        ("switch off ac", InputCommand("ac", "off", None)),
        ("switch on geyser", InputCommand("geyser", "on", None)),
        ("switch off geyser", InputCommand("geyser", "off", None)),
        ("switch on plug", InputCommand("plug", "on", None)),
        ("switch off plug", InputCommand("plug", "off", None)),
        ("switch on exhaust", InputCommand("exhaust", "on", None)),
        ("switch off exhaust", InputCommand("exhaust", "off", None)),
        ("switch on garden lights", InputCommand("garden lights", "on", None)),
        ("switch off garden lights", InputCommand("garden lights", "off", None)),

        # Vosk normalization: "t v" -> "tv"
        ("switch on t v", InputCommand("tv", "on", None)),
        ("switch off t v", InputCommand("tv", "off", None)),

        # Delayed commands with "switch on/off"
        ("switch on fan in 10 minutes", InputCommand("fan", "on", 10)),
        ("switch off light in 30 minutes", InputCommand("light", "off", 30)),
        ("switch on tv in 5 minutes", InputCommand("tv", "on", 5)),
        ("switch off ac in 15 minutes", InputCommand("ac", "off", 15)),

        # Legacy "turn on/off" still supported
        ("turn on light", InputCommand("light", "on", None)),
        ("turn off light", InputCommand("light", "off", None)),
        ("turn on fan", InputCommand("fan", "on", None)),
        ("turn off fan", InputCommand("fan", "off", None)),
        ("turn on fan in 10 minutes", InputCommand("fan", "on", 10)),
        ("turn off light in 30 minutes", InputCommand("light", "off", 30)),
        ("turn on air conditioner", InputCommand("ac", "on", None)),
        ("turn off television", InputCommand("tv", "off", None)),
        ("turn on garden lights", InputCommand("garden lights", "on", None)),
        ("turn off garden light", InputCommand("garden lights", "off", None)),
        ("turn on plug in 5 minutes", InputCommand("plug", "on", 5)),
        ("turn off exhaust in 15 minutes", InputCommand("exhaust", "off", 15)),

        # "turn the X on/off" still supported
        ("turn the light on", InputCommand("light", "on", None)),
        ("turn the fan off", InputCommand("fan", "off", None)),
    ]

    for text, expected in test_cases:
        result = parse_command(text)
        assert result.appliance == expected.appliance, f"Appliance mismatch for '{text}': got {result.appliance}, expected {expected.appliance}"
        assert result.action == expected.action, f"Action mismatch for '{text}': got {result.action}, expected {expected.action}"
        assert result.delay_minutes == expected.delay_minutes, f"Delay mismatch for '{text}': got {result.delay_minutes}, expected {expected.delay_minutes}"
        print(f"OK '{text}' -> {result}")


def test_invalid_commands():
    invalid_cases = [
        "switch on helicopter",
        "switch blue fan",
        "switch on fan in -5 minutes",
        "random words",
        "",
        "switch on",
        "turn on",
        "switch on unknown_device",
        "turn on unknown_device",
    ]

    for text in invalid_cases:
        try:
            parse_command(text)
            print(f"FAIL '{text}' should have failed but didn't")
        except VoiceParserError as e:
            print(f"OK '{text}' correctly rejected: {e}")


if __name__ == "__main__":
    print("Testing valid commands...")
    test_valid_commands()
    print("\nTesting invalid commands...")
    test_invalid_commands()
    print("\nAll tests passed!")