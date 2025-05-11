# test_configs.py

import pytest
from shared.client_configs import (
    health,
    list_config,
    set_config,
    get_config,
    remove_config,
    bulk_set_config,
    bulk_get_config,
    config
)

def unique_testkey(base):
    import uuid
    return f"test_{base}_{uuid.uuid4().hex[:8]}"

@pytest.fixture(autouse=True)
def config_key_tracker():
    """Yields a tracker to register and auto-cleanup new keys for each test."""
    touched_keys = []
    touched_scoped_keys = []
    initial_keys = set(list_config().keys())
    initial_scoped_keys = {}
    yield touched_keys, touched_scoped_keys

    # Clean up only new keys we touched
    for k in touched_keys:
        if k not in initial_keys:
            try:
                remove_config(k)
            except Exception:
                pass
    for scope, ks in touched_scoped_keys:
        pre = initial_scoped_keys.get(scope) or set(list_config(scope=scope).keys())
        for k in ks:
            if k not in pre:
                try:
                    remove_config(k, scope=scope)
                except Exception:
                    pass

def add_key_for_cleanup(k, scope=None, keylist=None, scopelist=None):
    if scope and scope != "global":
        scopelist.append((scope, [k]))
    else:
        keylist.append(k)

def test_health():
    out = health()
    assert out.get("status") == "ok"

def test_set_list_get_remove(config_key_tracker):
    keylist, _ = config_key_tracker
    k = unique_testkey("foo")
    set_config(k, "bar")
    keylist.append(k)

    items = list_config()
    assert items.get(k) == "bar"

    val = get_config(k)
    assert val == "bar"

    set_config(k, "baz")
    assert get_config(k) == "baz"

    remove_config(k)
    keylist.remove(k)

    with pytest.raises(Exception):
        get_config(k)
    with pytest.raises(Exception):
        remove_config(k)

def test_multiple_entries(config_key_tracker):
    keylist, _ = config_key_tracker
    data = {
        unique_testkey("a"): "1",
        unique_testkey("b"): "2",
        unique_testkey("c"): "hello"
    }
    for k, v in data.items():
        set_config(k, v)
        keylist.append(k)

    items = list_config()
    for k, v in data.items():
        assert items.get(k) == v

    for k in data.keys():
        remove_config(k)
        keylist.remove(k)

    assert all(k not in list_config() for k in data.keys())

def test_bulk_set_bulk_get_remove_all(config_key_tracker):
    keylist, _ = config_key_tracker
    items = {
        unique_testkey("aa"): "11",
        unique_testkey("bb"): "22",
        unique_testkey("cc"): "33"
    }
    bulk_set_config(items)
    keylist.extend(items.keys())

    values = bulk_get_config(list(items.keys()))
    assert values == items

    for k in items.keys():
        remove_config(k)
        keylist.remove(k)

    assert all(k not in list_config() for k in items.keys())

def test_bulk_set_partial_bulk_get_missing(config_key_tracker):
    keylist, _ = config_key_tracker
    items = {
        unique_testkey("x"): "1",
        unique_testkey("y"): "2"
    }
    bulk_set_config(items)
    keylist.extend(items.keys())

    keys = list(items.keys()) + [unique_testkey("z")]
    result = bulk_get_config(keys)

    for k in items.keys():
        assert result[k] == items[k]

    # The last key ("z") was never set, so it shouldn’t appear
    assert keys[-1] not in result

def test_scope_isolation(config_key_tracker):
    _, scopelist = config_key_tracker
    base = unique_testkey("abc")

    # set a global key
    set_config(base, "def")
    # set a scoped key under a unique test‐only scope name
    scope = unique_testkey("scope")
    set_config(base, "zzz", scope=scope)
    scopelist.append((scope, [base]))

    # global vs scoped should be isolated
    assert get_config(base) == "def"
    assert get_config(base, scope=scope) == "zzz"

    # remove the last key in the scope → that scope block should vanish
    remove_config(base, scope=scope)
    with pytest.raises(Exception):
        get_config(base, scope=scope)

    # global still there
    assert get_config(base) == "def"
    remove_config(base)

def test_remove_missing_config():
    # No setup needed, tries to remove a random test key.
    k = unique_testkey("not_present")
    with pytest.raises(Exception):
        remove_config(k)

def test_bulk_get_empty():
    # No keys given = should return {}
    out = bulk_get_config([])
    assert out == {}

def test_configdict_behaves_like_dict(config_key_tracker):
    keylist, _ = config_key_tracker
    config.clear_cache()
    k = unique_testkey("foo")
    config[k] = "X"
    keylist.append(k)

    assert config[k] == "X"
    assert k in config

    del_ok = False
    try:
        remove_config(k)
        keylist.remove(k)
        del_ok = True
    except Exception:
        pass

    assert del_ok

def test_bulk_set_and_bulk_get_scoped(config_key_tracker):
    _, scopelist = config_key_tracker
    A = unique_testkey("A")
    B = unique_testkey("B")

    # use a unique test‐only scope name
    scope = unique_testkey("scope")
    bulk_set_config({A: "1", B: "2"}, scope=scope)
    scopelist.append((scope, [A, B]))

    vals = bulk_get_config([A, B], scope=scope)
    assert vals == {A: "1", B: "2"}

    # remove both keys; the empty scope block should be pruned
    remove_config(A, scope=scope)
    remove_config(B, scope=scope)
    assert bulk_get_config([A, B], scope=scope) == {}
