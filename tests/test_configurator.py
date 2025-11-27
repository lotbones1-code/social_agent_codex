import configurator


def test_parse_delimited_list_supports_template_delimiter():
    raw = "alpha||beta|| gamma"

    result = configurator.parse_delimited_list(raw)

    assert result == ["alpha", "beta", "gamma"]


def test_parse_delimited_list_supports_commas_and_newlines():
    raw = "alpha, beta\ngamma"

    result = configurator.parse_delimited_list(raw)

    assert result == ["alpha", "beta", "gamma"]


def test_parse_delimited_list_ignores_empty_entries():
    raw = "alpha|| ||, ,beta\n\n,\tgamma"

    result = configurator.parse_delimited_list(raw)

    assert result == ["alpha", "beta", "gamma"]


def test_main_creates_env_file(tmp_path, capsys):
    env_path = tmp_path / ".env"
    assert not env_path.exists()

    result_path = configurator.main([str(tmp_path)])

    captured = capsys.readouterr()
    assert "Environment file ensured" in captured.out
    assert result_path == env_path
    assert env_path.exists()
