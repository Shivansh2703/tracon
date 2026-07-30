from tracon.trace.privacy import Tokenizer, args_shape, content_chars


def _tok(tmp_path, monkeypatch) -> Tokenizer:
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    return Tokenizer()


def test_token_stable_and_distinct(tmp_path, monkeypatch):
    tok = _tok(tmp_path, monkeypatch)
    a1 = tok.token("/Users/x/project")
    a2 = tok.token("/Users/x/project")
    b = tok.token("/Users/x/other")
    assert a1 == a2
    assert a1 != b
    assert a1.startswith("t_")
    assert "/Users" not in a1


def test_token_stable_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    assert Tokenizer().token("x") == Tokenizer().token("x")


def test_token_none_and_empty(tmp_path, monkeypatch):
    tok = _tok(tmp_path, monkeypatch)
    assert tok.token(None) is None
    assert tok.token("") is None


def test_salt_file_created_once(tmp_path, monkeypatch):
    salt_file = tmp_path / "nested" / "salt"
    monkeypatch.setenv("TRACON_SALT_FILE", str(salt_file))
    Tokenizer().token("x")
    first = salt_file.read_bytes()
    Tokenizer().token("y")
    assert salt_file.read_bytes() == first


def test_args_shape_never_contains_values():
    shape = args_shape({"command": "rm -rf /secret/path", "description": "boom", "n": 3})
    assert shape == "command:s19,description:s4,n:i"
    assert "secret" not in shape


def test_args_shape_types():
    shape = args_shape(
        {"s": "ab", "i": 1, "f": 1.5, "b": True, "none": None, "arr": [1, 2], "obj": {"k": 1}}
    )
    assert shape == "arr:a2,b:b,f:f,i:i,none:n,obj:o1,s:s2"


def test_args_shape_non_dict():
    assert args_shape(None) == "n"
    assert args_shape("text") == "s4"


def test_content_chars():
    assert content_chars("hello") == 5
    assert (
        content_chars([{"type": "text", "text": "abc"}, {"type": "thinking", "thinking": "de"}])
        == 5
    )
    assert content_chars([{"type": "tool_result", "content": "xyz"}]) == 3
    assert content_chars(["raw"]) == 3
    assert content_chars(None) == 0
    assert content_chars(42) == 0
