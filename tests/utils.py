import pytest

from logger import get_logger
from app.application import serialize


class TestUtils:

    def test_serialize(self, caplog):
        """
        """
        class Toto:
            value = 1
        
        @serialize
        def check_it():
            return Toto()
        expected_message = "serialize property or function is not implemented on <class 'utils.TestUtils.test_serialize.<locals>.Toto'>"
        with pytest.raises(NotImplementedError, match=expected_message) as error:
            s = check_it()
        assert "serialize property or function is not implemented" in caplog.text
        assert 'ERROR' in caplog.text
    
    def test_logger(self, caplog):
        """
        """
        get_logger().debug("Debug")
        assert caplog.text == ""
        get_logger().info("Info")
        assert "Info" in caplog.text
        get_logger().warn("Warn")
        assert "Warn" in caplog.text
        get_logger().error("Error")
        assert "Error" in caplog.text
        get_logger().critical("Critical")
        assert "Critical" in caplog.text