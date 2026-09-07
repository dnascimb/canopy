def test_cli_commands(runner):
    assert "Database ready" in runner.invoke(args=["init-db"]).output
    assert "Demo data loaded" in runner.invoke(args=["seed-demo"]).output
    out = runner.invoke(args=["export-markdown"]).output
    assert "## Timeline" in out
    assert '"schema": 1' in runner.invoke(args=["export-json"]).output
