from idlemypyextension.result import Result


class Dummy:
    """Dummy class."""

    __slots__ = ("x",)

    def __init__(self, x: str) -> None:
        self.x = x

    def __eq__(self, other: object) -> bool:
        """Return of other is also a dummy and has the same value."""
        return isinstance(other, Dummy) and other.x == self.x


def test_ok_construction() -> None:
    # simple primitive
    r_int = Result.ok(123)
    assert r_int.success is True
    assert r_int.value == 123
    # generic object
    obj = Dummy("hello")
    r_obj = Result.ok(obj)
    assert r_obj.success is True
    assert r_obj.value == obj


def test_fail_construction() -> None:
    r_str = Result.fail("error")
    assert r_str.success is False
    assert r_str.value == "error"
    # also with None
    r_none = Result.fail(None)
    assert not r_none.success
    assert r_none.value is None


def test_bool_truthiness() -> None:
    r1 = Result.ok("yay")
    r2 = Result.fail("nay")
    # __bool__ returns success
    assert bool(r1) is True
    assert r1  # truthy
    assert bool(r2) is False
    assert not r2  # falsy


def test_unwrap_returns_value() -> None:
    val = {"a": 1}
    r = Result.ok(val)
    assert r.unwrap() is val

    err = ["oops"]
    r2 = Result.fail(err)
    # unwrap simply returns the value regardless of success
    assert r2.unwrap() == ["oops"]


def test_equality_and_tuple_behavior() -> None:
    # NamedTuple guarantees tuple-like behavior & equality
    r1 = Result.ok(10)
    r2 = Result(True, 10)
    assert r1 == r2
    # Different success or value should not be equal
    assert Result.fail(10) != r1
    assert Result.ok(11) != r1


def test_repr_and_str_contains_fields() -> None:
    # basic smoke-test for repr to contain field names and values
    r = Result.ok(42)
    rep = repr(r)
    assert "Result(success=True" in rep
    assert "value=42" in rep


def test_type_hints_do_not_break_runtime() -> None:
    # Confirm that generics don't interfere at runtime
    r_float: Result[float] = Result.ok(3.14)
    assert isinstance(r_float.value, float)
    assert r_float.success
