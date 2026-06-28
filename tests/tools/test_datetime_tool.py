from tapio.tools.datetime_tool import get_current_datetime
from tapio.tools import datetime_tool
from zoneinfo import ZoneInfoNotFoundError



def test_returns_string():
    result = get_current_datetime.invoke({})
    assert isinstance(result, str)
    assert len(result) > 0


def test_includes_timezone():
    result = get_current_datetime.invoke({})
    # Helsinki is EET (UTC+2) or EEST (UTC+3) depending on DST
    assert "EET" in result or "EEST" in result
    
    
def test_when_tzdata_missing(monkeypatch):
    """If the IANA timezone database isn't available, the tool should
    fall back to UTC."""
    
    def raise_zone_info_not_found(name):
        raise ZoneInfoNotFoundError(name)
    monkeypatch.setattr(datetime_tool, "ZoneInfo", raise_zone_info_not_found)

    result = get_current_datetime.invoke({})
    assert isinstance(result, str)
    assert len(result) > 0
    assert "UTC" in result