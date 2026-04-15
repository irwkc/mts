ннfrom app.log_sanitize import format_json_for_log, redact_for_log


def test_redact_sk_in_string():
    d = {"messages": [{"role": "user", "content": "use sk-12345678901234567890please"}]}
    r = redact_for_log(d)
    assert "sk-***REDACTED***" in str(r["messages"][0]["content"])


def test_redact_sensitive_keys():
    d = {"api_key": "secret", "nested": {"password": "x"}}
    r = redact_for_log(d)
    assert r["api_key"] == "***REDACTED***"
    assert r["nested"]["password"] == "***REDACTED***"


def test_format_json_truncates():
    long_text = "a" * 100
    d = {"t": long_text}
    s = format_json_for_log(d, max_chars=50)
    assert "truncated" in s or len(s) <= 55
