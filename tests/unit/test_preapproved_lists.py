"""Tests for preapproved_lists.py — PreApprovedListManager with mocked Redis"""
import sys, os, unittest
from unittest.mock import MagicMock, patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "trust-registry"))
from preapproved_lists import (
    PreApprovedListManager, ListType, COMMON_LISTS, initialize_common_lists
)


class TestPreApprovedListManager(unittest.TestCase):
    def setUp(self):
        self.redis = MagicMock()
        self.mgr = PreApprovedListManager(self.redis)

    def test_create_list(self):
        self.assertTrue(
            self.mgr.create_list("VENDORS", ListType.WHITELIST, ["A", "B"], "desc")
        )
        self.redis.hset.assert_called_once()
        self.redis.sadd.assert_any_call("list:VENDORS", "A", "B")
        self.redis.sadd.assert_any_call("lists:registry", "VENDORS")

    def test_create_list_empty_items(self):
        self.assertTrue(self.mgr.create_list("EMPTY", ListType.BLACKLIST, []))
        # sadd should only be called for registry, not for empty items
        self.redis.sadd.assert_called_once_with("lists:registry", "EMPTY")

    def test_create_list_exception(self):
        self.redis.hset.side_effect = Exception("boom")
        self.assertFalse(self.mgr.create_list("FAIL", ListType.WHITELIST, ["A"]))

    def test_add_items(self):
        self.redis.sadd.return_value = 2
        result = self.mgr.add_items("VENDORS", ["C", "D"])
        self.assertEqual(result, 2)

    def test_add_items_exception(self):
        self.redis.sadd.side_effect = Exception("boom")
        self.assertEqual(self.mgr.add_items("VENDORS", ["C"]), 0)

    def test_remove_items(self):
        self.redis.srem.return_value = 1
        result = self.mgr.remove_items("VENDORS", ["A"])
        self.assertEqual(result, 1)

    def test_remove_items_exception(self):
        self.redis.srem.side_effect = Exception("boom")
        self.assertEqual(self.mgr.remove_items("VENDORS", ["A"]), 0)

    def test_check_membership(self):
        self.redis.sismember.return_value = True
        self.assertTrue(self.mgr.check_membership("VENDORS", "A"))

    def test_get_list(self):
        self.redis.hgetall.return_value = {
            "name": b"VENDORS", "type": b"whitelist", "description": b"d"
        }
        self.redis.smembers.return_value = {b"A", b"B"}
        result = self.mgr.get_list("VENDORS")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "whitelist")

    def test_get_list_not_found(self):
        self.redis.hgetall.return_value = {}
        self.assertIsNone(self.mgr.get_list("NOPE"))

    def test_get_list_exception(self):
        self.redis.hgetall.side_effect = Exception("boom")
        self.assertIsNone(self.mgr.get_list("FAIL"))

    def test_list_all(self):
        self.redis.smembers.return_value = {"VENDORS", "BLOCKED"}
        result = self.mgr.list_all()
        self.assertEqual(len(result), 2)

    def test_list_all_exception(self):
        self.redis.smembers.side_effect = Exception("boom")
        self.assertEqual(self.mgr.list_all(), [])

    def test_delete_list(self):
        self.assertTrue(self.mgr.delete_list("VENDORS"))
        self.assertEqual(self.redis.delete.call_count, 2)
        self.redis.srem.assert_called_once_with("lists:registry", "VENDORS")

    def test_delete_list_exception(self):
        self.redis.delete.side_effect = Exception("boom")
        self.assertFalse(self.mgr.delete_list("VENDORS"))


class TestInitializeCommonLists(unittest.TestCase):
    def test_initializes_all(self):
        mgr = MagicMock()
        initialize_common_lists(mgr)
        self.assertEqual(mgr.create_list.call_count, len(COMMON_LISTS))

    def test_blocked_uses_blacklist_type(self):
        mgr = MagicMock()
        initialize_common_lists(mgr)
        # Find the call with BLOCKED_COUNTRIES
        for call in mgr.create_list.call_args_list:
            if call[1].get("list_name", call[0][0] if call[0] else "") == "BLOCKED_COUNTRIES":
                self.assertEqual(call[1].get("list_type", call[0][1] if len(call[0]) > 1 else None), ListType.BLACKLIST)
                break


class TestListType(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(ListType.WHITELIST.value, "whitelist")
        self.assertEqual(ListType.BLACKLIST.value, "blacklist")


if __name__ == "__main__":
    unittest.main()


class TestPreApprovedLists:

    def _make_manager(self):
        from preapproved_lists import PreApprovedListManager
        mock_redis = MagicMock()
        return PreApprovedListManager(mock_redis), mock_redis

    def test_create_list(self):
        from preapproved_lists import ListType
        mgr, r = self._make_manager()
        assert mgr.create_list("vendors", ListType.WHITELIST, ["V1", "V2"]) is True
        r.hset.assert_called_once()
        r.sadd.assert_called()

    def test_create_list_empty_items(self):
        from preapproved_lists import ListType
        mgr, r = self._make_manager()
        assert mgr.create_list("empty", ListType.BLACKLIST, []) is True

    def test_create_list_error(self):
        from preapproved_lists import ListType
        mgr, r = self._make_manager()
        r.hset.side_effect = Exception("redis down")
        assert mgr.create_list("vendors", ListType.WHITELIST, ["V1"]) is False

    def test_add_items(self):
        mgr, r = self._make_manager()
        r.sadd.return_value = 2
        assert mgr.add_items("vendors", ["V3", "V4"]) == 2

    def test_add_items_error(self):
        mgr, r = self._make_manager()
        r.sadd.side_effect = Exception("fail")
        assert mgr.add_items("vendors", ["V3"]) == 0

    def test_remove_items(self):
        mgr, r = self._make_manager()
        r.srem.return_value = 1
        assert mgr.remove_items("vendors", ["V1"]) == 1

    def test_remove_items_error(self):
        mgr, r = self._make_manager()
        r.srem.side_effect = Exception("fail")
        assert mgr.remove_items("vendors", ["V1"]) == 0

    def test_check_membership(self):
        mgr, r = self._make_manager()
        r.sismember.return_value = True
        assert mgr.check_membership("vendors", "V1") is True

    def test_get_list_found(self):
        mgr, r = self._make_manager()
        r.hgetall.return_value = {
            "name": b"vendors", "type": b"whitelist", "description": b"desc"
        }
        r.smembers.return_value = {b"V1", b"V2"}
        result = mgr.get_list("vendors")
        assert result is not None
        assert result["name"] == "vendors"

    def test_get_list_not_found(self):
        mgr, r = self._make_manager()
        r.hgetall.return_value = {}
        assert mgr.get_list("missing") is None

    def test_get_list_error(self):
        mgr, r = self._make_manager()
        r.hgetall.side_effect = Exception("fail")
        assert mgr.get_list("vendors") is None

    def test_list_all(self):
        mgr, r = self._make_manager()
        r.smembers.return_value = {b"list1", b"list2"}
        result = mgr.list_all()
        assert len(result) == 2

    def test_list_all_error(self):
        mgr, r = self._make_manager()
        r.smembers.side_effect = Exception("fail")
        assert mgr.list_all() == []

    def test_delete_list(self):
        mgr, r = self._make_manager()
        assert mgr.delete_list("vendors") is True
        assert r.delete.call_count == 2

    def test_delete_list_error(self):
        mgr, r = self._make_manager()
        r.delete.side_effect = Exception("fail")
        assert mgr.delete_list("vendors") is False

    def test_initialize_common_lists(self):
        from preapproved_lists import initialize_common_lists
        mock_mgr = MagicMock()
        initialize_common_lists(mock_mgr)
        assert mock_mgr.create_list.call_count == 4


# ────────────────────── recursive_parser.py ───────────────────────────────


