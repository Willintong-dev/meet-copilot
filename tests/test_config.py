from meet_copilot.config import Settings, account_first_name, load_settings


def test_user_name_defaults_to_the_account_first_name(monkeypatch):
    monkeypatch.setattr("meet_copilot.config.account_first_name", lambda: "Ana")
    assert Settings().user_name == "Ana"


def test_account_first_name_is_never_empty():
    assert account_first_name().strip()


def test_config_file_overrides_defaults(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(f'home = "{tmp_path}"\nuser_name = "Luis"\nanswer_length = "breve"\nunknown = 1\n')
    settings = load_settings(config)
    assert (settings.user_name, settings.answer_length) == ("Luis", "breve")
    assert settings.briefs_dir.is_dir()
