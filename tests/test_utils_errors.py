import unittest

from utils.errors import AgentError, ConfigError


class AgentErrorTests(unittest.TestCase):
    def test_is_an_exception_carrying_its_message(self):
        err = AgentError("something broke")
        self.assertIsInstance(err, Exception)
        self.assertEqual(err.message, "something broke")
        self.assertEqual(str(err), "something broke")

    def test_details_default_to_an_empty_dict_rather_than_none(self):
        # Callers read .details without guarding, so None would be a crash.
        self.assertEqual(AgentError("x").details, {})

    def test_details_are_appended_to_the_string(self):
        err = AgentError("bad request", details={"status": 400, "path": "/runs"})
        self.assertEqual(str(err), "bad request (status=400, path=/runs)")

    def test_the_cause_is_appended_to_the_string(self):
        err = AgentError("write failed", cause=OSError("disk full"))
        self.assertEqual(str(err), "write failed [caused by: disk full]")

    def test_details_and_cause_both_appear(self):
        err = AgentError("write failed", details={"path": "/tmp/x"}, cause=OSError("disk full"))
        self.assertEqual(str(err), "write failed (path=/tmp/x) [caused by: disk full]")

    def test_to_dict_reports_the_concrete_class(self):
        payload = ConfigError("nope").to_dict()
        self.assertEqual(payload["type"], "ConfigError")

    def test_to_dict_stringifies_the_cause_and_nulls_it_when_absent(self):
        self.assertIsNone(AgentError("x").to_dict()["cause"])
        self.assertEqual(AgentError("x", cause=ValueError("why")).to_dict()["cause"], "why")

    def test_to_dict_carries_the_message_and_details(self):
        payload = AgentError("boom", details={"k": "v"}).to_dict()
        self.assertEqual(payload["message"], "boom")
        self.assertEqual(payload["details"], {"k": "v"})


class ConfigErrorTests(unittest.TestCase):
    def test_is_an_agent_error(self):
        self.assertIsInstance(ConfigError("nope"), AgentError)

    def test_folds_the_config_fields_into_details(self):
        err = ConfigError("missing key", config_key="model", config_file="postal.toml")
        self.assertEqual(err.details, {"config_key": "model", "config_file": "postal.toml"})
        self.assertEqual(err.config_key, "model")
        self.assertEqual(err.config_file, "postal.toml")

    def test_keeps_details_the_caller_passed_alongside_them(self):
        err = ConfigError("missing key", config_key="model", details={"line": 12})
        self.assertEqual(err.details, {"line": 12, "config_key": "model"})

    def test_omits_the_config_fields_that_were_not_given(self):
        self.assertEqual(ConfigError("bad file", config_file="postal.toml").details, {"config_file": "postal.toml"})
        self.assertIsNone(ConfigError("bad file", config_file="postal.toml").config_key)

    def test_still_takes_a_cause(self):
        err = ConfigError("unreadable", config_file="postal.toml", cause=OSError("denied"))
        self.assertEqual(err.to_dict()["cause"], "denied")


if __name__ == "__main__":
    unittest.main()
