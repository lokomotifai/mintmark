"""Invariant 11: no float reaches emitted data, and the bytes are canonical.

`reproduce` compares files byte for byte, so serialization is part of the
determinism contract rather than a presentation detail. Key order, escaping,
line endings, and the trailing newline are all asserted here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mintmark.emit import (
    FloatInOutputError,
    SpreadsheetFormulaError,
    csv_header,
    render_csv_row,
    render_record,
    staged_output,
)

ORDER = ("customer_id", "first_name", "balance_kurus", "currency", "note")
RECORD = {
    "customer_id": "CUST-00000000",
    "first_name": "Ayşe",
    "balance_kurus": 2_504_134,
    "currency": "TRY",
    "note": None,
}


def test_keys_are_written_in_declaration_order_not_sorted() -> None:
    line = render_record(RECORD, ORDER)
    assert line.index('"customer_id"') < line.index('"first_name"')
    assert line.index('"first_name"') < line.index('"balance_kurus"')
    # Sorted order would put balance_kurus first; insertion order is not enough
    # of a guarantee either, since a generator may build a record any way it likes.
    reversed_input = {name: RECORD[name] for name in reversed(ORDER)}
    assert render_record(reversed_input, ORDER) == line


def test_turkish_characters_appear_literally() -> None:
    line = render_record(RECORD, ORDER)
    assert "Ayşe" in line
    assert "\\u" not in line


def test_the_line_is_compact_with_no_incidental_whitespace() -> None:
    line = render_record(RECORD, ORDER)
    assert ", " not in line
    assert ": " not in line
    assert "\n" not in line


def test_the_line_round_trips_through_a_json_parser() -> None:
    assert json.loads(render_record(RECORD, ORDER)) == RECORD


def test_null_is_written_as_json_null() -> None:
    assert '"note":null' in render_record(RECORD, ORDER)


@pytest.mark.parametrize(
    "value",
    [1.5, 0.0, -2.25, float("1e10")],
)
def test_a_float_field_is_refused(value: float) -> None:
    record = {**RECORD, "balance_kurus": value}
    with pytest.raises(FloatInOutputError, match="integer kurus"):
        render_record(record, ORDER)


def test_a_float_nested_inside_a_field_is_refused() -> None:
    """The encoder's default hook never sees a float, so the walk has to."""
    record = {**RECORD, "note": {"ratio": 0.5}}
    with pytest.raises(FloatInOutputError, match="reached emission"):
        render_record(record, ORDER)


def test_a_float_inside_a_list_is_refused() -> None:
    record = {**RECORD, "note": [1, 2, 3.5]}
    with pytest.raises(FloatInOutputError):
        render_record(record, ORDER)


def test_the_error_names_where_the_float_was_found() -> None:
    record = {**RECORD, "note": {"nested": {"deep": 0.25}}}
    with pytest.raises(FloatInOutputError, match=r"note\.nested\.deep"):
        render_record(record, ORDER)


def test_a_missing_declared_field_is_refused() -> None:
    """A shorter line would push the disagreement into the consumer's parser."""
    record = {name: RECORD[name] for name in ORDER if name != "currency"}
    with pytest.raises(ValueError, match="missing declared fields"):
        render_record(record, ORDER)


def test_an_undeclared_field_is_refused() -> None:
    with pytest.raises(ValueError, match="undeclared fields"):
        render_record({**RECORD, "surprise": 1}, ORDER)


def test_csv_header_and_row_share_the_declaration_order() -> None:
    header = csv_header(ORDER)
    row = render_csv_row(RECORD, ORDER)
    assert header == "customer_id,first_name,balance_kurus,currency,note\n"
    assert row.startswith("CUST-00000000,Ayşe,2504134,TRY,")
    assert header.endswith("\n")
    assert row.endswith("\n")


def test_csv_null_becomes_an_empty_cell() -> None:
    assert render_csv_row(RECORD, ORDER).rstrip("\n").endswith(",")


def test_csv_quotes_a_cell_containing_a_separator() -> None:
    record = {**RECORD, "first_name": 'Ayşe, "kısa"'}
    row = render_csv_row(record, ORDER)
    assert '"Ayşe, ""kısa"""' in row


def test_csv_refuses_a_nested_value_rather_than_inventing_a_convention() -> None:
    record = {**RECORD, "note": {"a": 1}}
    with pytest.raises(TypeError, match="no CSV representation"):
        render_csv_row(record, ORDER)


def test_csv_refuses_a_float() -> None:
    with pytest.raises(TypeError, match="integer kurus"):
        render_csv_row({**RECORD, "balance_kurus": 1.5}, ORDER)


def test_csv_refuses_spreadsheet_formula_cells_including_prefixed_forms() -> None:
    for value in ("=1+1", "+SUM(A1:A2)", "-2+3", "@cmd", '\t =HYPERLINK("x")'):
        with pytest.raises(SpreadsheetFormulaError, match="active cells"):
            render_csv_row({**RECORD, "first_name": value}, ORDER)
    assert "+90 555 123 45 67" in render_csv_row(
        {**RECORD, "first_name": "+90 555 123 45 67"}, ORDER
    )
    with pytest.raises(SpreadsheetFormulaError):
        render_csv_row({**RECORD, "first_name": "+90 1+1"}, ORDER)


def test_a_completed_mint_appears_at_its_target_path(tmp_path: Path) -> None:
    target = tmp_path / "run"
    with staged_output(target) as staged:
        with staged.open("customer.jsonl") as handle:
            handle.write(render_record(RECORD, ORDER) + "\n")
        assert not target.exists(), "output was visible before the mint completed"
    assert target.is_dir()
    assert (target / "customer.jsonl").read_text(encoding="utf-8").endswith("\n")


def test_an_interrupted_mint_leaves_nothing_behind(tmp_path: Path) -> None:
    """Either a complete mint or no directory. Never something in between."""
    target = tmp_path / "run"

    def interrupted() -> None:
        with staged_output(target) as staged, staged.open("customer.jsonl") as handle:
            handle.write("partial")
            raise RuntimeError("interrupted mid-mint")

    with pytest.raises(RuntimeError, match="interrupted mid-mint"):
        interrupted()

    assert not target.exists()
    assert list(tmp_path.iterdir()) == [], "a staging directory survived the failure"


def test_a_keyboard_interrupt_also_cleans_up(tmp_path: Path) -> None:
    """KeyboardInterrupt is a BaseException, so `except Exception` would miss it."""
    target = tmp_path / "run"

    def interrupted() -> None:
        with staged_output(target) as staged:
            staged.open("x.jsonl").close()
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        interrupted()
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_an_existing_output_directory_is_never_overwritten(tmp_path: Path) -> None:
    """The directory in the way may be a published dataset."""
    target = tmp_path / "run"
    target.mkdir()
    (target / "precious.jsonl").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="never overwrites"), staged_output(target) as staged:
        staged.open("customer.jsonl").close()

    assert (target / "precious.jsonl").read_text(encoding="utf-8") == "keep me\n"


def test_files_are_written_with_lf_endings(tmp_path: Path) -> None:
    with staged_output(tmp_path / "run") as staged, staged.open("data.jsonl") as handle:
        handle.write("first\nsecond\n")
    raw = (tmp_path / "run" / "data.jsonl").read_bytes()
    assert b"\r\n" not in raw
    assert raw == b"first\nsecond\n"


def test_concurrent_staging_directories_never_share_bytes(tmp_path: Path) -> None:
    target = tmp_path / "run"

    def race() -> None:
        with staged_output(target) as first, staged_output(target) as second:
            assert first.path != second.path
            with first.open("data.jsonl") as handle:
                handle.write("first\n")
            with second.open("data.jsonl") as handle:
                handle.write("second\n")
            first.commit()

    with pytest.raises(FileExistsError):
        race()

    assert (target / "data.jsonl").read_text(encoding="utf-8") == "first\n"
    assert list(tmp_path.glob(".run.staging-*")) == []


def test_staged_output_refuses_parent_traversal(tmp_path: Path) -> None:
    with staged_output(tmp_path / "run") as staged:
        with pytest.raises(ValueError, match="single file names"):
            staged.open("../escape.jsonl")
        staged.open("safe.jsonl").close()
    assert not (tmp_path / "escape.jsonl").exists()


def test_staged_output_does_not_follow_a_preplanted_leaf_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_text("keep\n", encoding="utf-8")
    with staged_output(tmp_path / "run") as staged:
        (staged.path / "data.jsonl").symlink_to(outside)
        with pytest.raises(FileExistsError):
            staged.open("data.jsonl")
        (staged.path / "data.jsonl").unlink()
        staged.open("safe.jsonl").close()
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_a_sigterm_during_a_mint_also_cleans_up(tmp_path: Path) -> None:
    """SIGTERM's default disposition ends the process before any cleanup runs.

    For the duration of a mint it is turned into an exception, so the staging
    directory is discarded and the process still exits the way a terminated
    process does.
    """
    import os
    import signal

    if signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL:
        pytest.skip("the host installed its own SIGTERM handler; the mint must leave it alone")
    target = tmp_path / "run"

    def terminated() -> None:
        with staged_output(target) as staged:
            staged.open("x.jsonl").close()
            os.kill(os.getpid(), signal.SIGTERM)
            for _ in range(10_000):  # give the handler a bytecode boundary to run at
                pass
            raise AssertionError("SIGTERM was not turned into an exception")

    with pytest.raises(SystemExit) as caught:
        terminated()
    assert caught.value.code == 128 + signal.SIGTERM
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL, (
        "the previous handler was not restored"
    )


def test_a_host_sigterm_handler_is_left_alone(tmp_path: Path) -> None:
    import signal

    def host_handler(signum: int, frame: object) -> None:  # pragma: no cover - never invoked
        del signum, frame

    previous = signal.signal(signal.SIGTERM, host_handler)
    try:
        with staged_output(tmp_path / "run") as staged:
            staged.open("x.jsonl").close()
            assert signal.getsignal(signal.SIGTERM) is host_handler
    finally:
        signal.signal(signal.SIGTERM, previous)
