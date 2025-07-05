from wickedlines import Colors, colorize_ev


def test_colorize_ev():
    assert colorize_ev(1.0) == Colors.GREEN + "+1.0" + Colors.END
