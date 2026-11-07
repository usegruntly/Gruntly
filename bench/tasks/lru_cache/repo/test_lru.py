from lru import LRUCache

def test_basic():
    c = LRUCache(2)
    c.put("a", 1)
    assert c.get("a") == 1
    assert c.get("zzz") is None
