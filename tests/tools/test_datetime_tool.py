from tapio.tools.datetime_tool import get_current_datetime


def test_returns_string():
    result = get_current_datetime.invoke({})
    assert isinstance(result, str)
    assert len(result) > 0


def test_includes_timezone():
    result = get_current_datetime.invoke({})
    # Helsinki is EET (UTC+2) or EEST (UTC+3) depending on DST
    assert "EET" in result or "EEST" in result