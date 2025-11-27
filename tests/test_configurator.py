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
