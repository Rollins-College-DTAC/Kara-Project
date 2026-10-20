"""Tests for the Live Run page's DOT flow-chart builder (dashboard/flow.py).

Pure string checks: no Streamlit import needed, so this runs in the normal test suite.
"""

from dashboard.flow import WAITING_COLOR, build_dot


def row(step, status="ok", message=""):
    return {"step": step, "status": status, "message": message, "rows_in": 1, "rows_out": 1, "rows_rejected": 0}


def test_unreached_steps_are_grey_and_reached_ones_are_colored():
    dot = build_dot([row("detect"), row("land")], decision=None)
    assert f'"detect" [label="Detect", fillcolor="forestgreen"' in dot
    assert f'"classify" [label="Classify", fillcolor="{WAITING_COLOR}"' in dot


def test_failed_step_is_red_and_running_step_is_blue():
    dot = build_dot([row("detect", status="failed"), row("land", status="running")], decision=None)
    assert '"detect" [label="Detect", fillcolor="firebrick"' in dot
    assert '"land" [label="Land\\n(TinyDB)", fillcolor="dodgerblue"' in dot


def test_held_decide_step_is_amber():
    dot = build_dot([row("decide", status="held")], decision={"fired": True})
    assert '"decide" [label="Decide", fillcolor="goldenrod"' in dot


def test_fired_trigger_takes_the_hold_branch_and_publish_is_dashed():
    dot = build_dot([row("decide"), row("act", status="held")], decision={"fired": True})
    assert '"decide" -> "publish" [style=dashed];' in dot
    assert '"decide" -> "hold";' in dot
    assert f'"hold" [label="Hold and alert", fillcolor="goldenrod"' in dot
    assert f'"publish" [label="Publish", fillcolor="{WAITING_COLOR}"' in dot


def test_not_fired_takes_the_publish_branch_and_hold_is_dashed():
    dot = build_dot([row("decide"), row("act", status="ok")], decision={"fired": False})
    assert '"decide" -> "publish";' in dot
    assert '"decide" -> "hold" [style=dashed];' in dot
    assert '"publish" [label="Publish", fillcolor="forestgreen"' in dot


def test_no_act_row_means_both_terminal_nodes_stay_grey():
    dot = build_dot([row("decide")], decision=None)
    assert f'"publish" [label="Publish", fillcolor="{WAITING_COLOR}"' in dot
    assert f'"hold" [label="Hold and alert", fillcolor="{WAITING_COLOR}"' in dot


def test_long_messages_are_shortened():
    dot = build_dot([row("detect", message="x" * 100)], decision=None)
    assert "…" in dot


def test_double_quotes_in_a_message_never_leak_into_the_dot_label():
    dot = build_dot([row("detect", message='file "weird name".csv landed')], decision=None)
    assert "'weird name'" in dot and '"weird name"' not in dot
