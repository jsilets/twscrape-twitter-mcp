"""CLI defaults stay compatible with MCP registry launchers."""

from twscrape_twitter_mcp import cli


def test_no_arguments_start_the_stdio_server():
    args = cli.build_parser().parse_args([])
    assert args.func is cli._cmd_serve
    assert args.transport == "stdio"


def test_login_defaults_to_a_dedicated_chrome_profile():
    args = cli.build_parser().parse_args(["login"])
    assert args.launch_browser == "chrome"


def test_login_attach_overrides_dedicated_browser_default():
    args = cli.build_parser().parse_args(["login", "--attach"])
    assert args.attach is True
