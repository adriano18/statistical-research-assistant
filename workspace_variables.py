"""Stage 37 (Issue #68, review UX-3, U2, D7): the variable panel of the role pickers.

A role that takes several variables (items, outcomes, covariates, the
variables related to one, predictors, repeated measurements) is chosen in a
panel that finds and selects many variables at once:

* **search**: a part of a name, a pattern with ``*`` and ``?``
  (``SYN_COPE_0*``), a range in column order (``SYN_LON_01..SYN_LON_20``),
  or several of these separated by commas; Enter in the field selects what
  is shown;
* **name groups**: numbered variables with one stem (``SYN_LON_01`` …
  ``SYN_LON_20``) are one button, "All SYN_LON_* (20)": a whole item set in
  one action;
* **select all shown**, **unselect shown**, **clear** and a visible count.

Only the variables the role can take are listed (D7): an identifier, a
variable already chosen for another role of the same analysis (the
grouping variable and the outcome are never offered as covariates) and a
variable whose confirmed measurement level the role does not take are left
out, and the panel says which and why, as text. Nothing is left out
silently, and nothing is chosen for the researcher: every selection is a
press of a button or a box, and the confirmations an analysis asks for are
untouched by the panel.

The logic (which variables a role offers, name groups, the filter) has no
Flet import. :func:`role_panel` builds the panel the Analyze page renders
on every change; :class:`PreparationItems` keeps its own state for the item
list of the hosted *Prepare data* panel (scale scores), which is built once.

Keyboard: the search field, the group and action buttons and the boxes are
ordinary focusable controls in reading order (Tab), buttons and boxes
answer Enter and Space, and every one is named by its visible text (its
label for UI Automation); the count and the reasons are plain text.
"""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import re
from typing import Callable, Iterable

# --------------------------------------------------------------- which variables


@dataclass(frozen=True)
class NotOffered:
    """A variable a role does not list, and why (``reason``):

    * ``identifier``: confirmed or suggested as an identifier;
    * ``role``: already chosen for another role (``detail``: its
      :func:`role_name`);
    * ``level``: its confirmed level is not one the role takes (``detail``:
      the level);
    * ``binary``: the role needs a 0/1 variable;
    * ``not_numeric``: not numeric (scale scores in Data → Prepare)."""

    name: str
    reason: str
    detail: str = ""


def role_name(role) -> str:
    """The suffix of the ``vars.role.*`` text that names a role in "already
    …": its key, and ``outcomes`` for an outcome among several."""
    return "outcomes" if role.key == "outcome" and role.multiple else role.key


def taken_by_others(roles: Iterable, selection: dict, role_key: str) -> dict[str, str]:
    """``{variable: role name}`` (:func:`role_name`) for the variables chosen
    for the roles other than ``role_key`` (the first role holding one wins)."""
    taken: dict[str, str] = {}
    for role in roles:
        if role.key == role_key:
            continue
        value = selection.get(role.key)
        for name in (value if isinstance(value, (list, tuple)) else [value] if value else []):
            if isinstance(name, str):
                taken.setdefault(name, role_name(role))
    return taken


def offered_variables(session, role, taken: dict[str, str]) -> tuple[list[str], list[NotOffered]]:
    """``(offered, not offered)`` for ``role``, both in column order.

    A variable whose level is not confirmed yet is offered: it is confirmed
    in the analysis itself (step 3, or the form's level fixes)."""
    offered: list[str] = []
    left_out: list[NotOffered] = []
    for info in session.variables.values():
        name = info.name
        if info.suggested == "id" or info.confirmed == "id":
            left_out.append(NotOffered(name, "identifier"))
        elif name in taken:
            left_out.append(NotOffered(name, "role", taken[name]))
        elif info.confirmed != "unknown" and info.confirmed not in role.levels:
            left_out.append(NotOffered(name, "level", info.confirmed))
        elif getattr(role, "binary", False) and not info.binary:
            left_out.append(NotOffered(name, "binary"))
        else:
            offered.append(name)
    return offered, left_out


# ------------------------------------------------------------------ name groups
_NUMBERED = re.compile(r"^(?P<stem>.*\D)(?P<number>\d+)$")


def name_groups(names: Iterable[str], minimum: int = 2) -> list[tuple[str, list[str]]]:
    """Numbered variables that share a stem, in column order:
    ``[("SYN_LON_", ["SYN_LON_01", …, "SYN_LON_20"]), …]``. A stem is the
    name up to its final run of digits and must not be empty; groups with
    fewer than ``minimum`` members are left out."""
    groups: dict[str, list[str]] = {}
    for name in names:
        match = _NUMBERED.match(str(name))
        if match:
            groups.setdefault(match["stem"], []).append(str(name))
    return [(stem, members) for stem, members in groups.items() if len(members) >= minimum]


def group_pattern(stem: str) -> str:
    return f"{stem}*"


# ----------------------------------------------------------------------- filter
_RANGE = re.compile(r"^(?P<first>.+?)\s*(?:\.\.|…|–|—|\s+to\s+)\s*(?P<last>.+)$", re.I)


def _range(term: str, order: list[str]) -> list[str] | None:
    """The names from ``first`` to ``last`` in column order (inclusive, either
    way round), when both ends are variables of ``order``; otherwise None."""
    match = _RANGE.match(term)
    if not match:
        return None
    position = {name.lower(): index for index, name in enumerate(order)}
    first = position.get(match["first"].strip().lower())
    last = position.get(match["last"].strip().lower())
    if first is None or last is None:
        return None
    low, high = sorted((first, last))
    return order[low:high + 1]


def _term_matches(term: str, names: list[str], order: list[str]) -> set[str]:
    span = _range(term, order)
    if span is not None:
        return set(span)
    if any(mark in term for mark in "*?["):
        pattern = term.lower()
        return {name for name in names if fnmatch.fnmatchcase(name.lower(), pattern)}
    if " " in term:          # several names separated by spaces
        found: set[str] = set()
        for part in term.split():
            found |= _term_matches(part, names, order)
        return found
    needle = term.lower()
    return {name for name in names if needle in name.lower()}


def filter_names(names: list[str], query: str, order: list[str] | None = None) -> list[str]:
    """The names of ``names`` that ``query`` shows, in their own order.

    ``query`` holds one or more terms separated by commas or semicolons; a
    term is a part of a name (any case), a pattern with ``*``, ``?`` or
    ``[…]``, or a range ``first..last`` (also ``first – last`` or ``first to
    last``) taken in ``order`` (the data's column order). Empty: all."""
    query = (query or "").strip()
    if not query:
        return list(names)
    order = list(order if order is not None else names)
    wanted: set[str] = set()
    for term in re.split(r"[,;]", query):
        term = term.strip()
        if term:
            wanted |= _term_matches(term, list(names), order)
    return [name for name in names if name in wanted]


def merged(chosen: list[str], added: Iterable[str]) -> list[str]:
    """``chosen`` followed by the names of ``added`` it lacks, in their order."""
    result = list(chosen)
    for name in added:
        if name not in result:
            result.append(name)
    return result


# --------------------------------------------------------------- reasons as text
SHOWN_NAMES = 8           # names listed per reason before "and N more"


def _names_text(ui, names: list[str]) -> str:
    if len(names) <= SHOWN_NAMES:
        return ", ".join(names)
    return ui.t("vars.more", names=", ".join(names[:SHOWN_NAMES]),
                count=len(names) - SHOWN_NAMES)


def not_offered_lines(ui, left_out: list[NotOffered], allowed: Iterable[str] = ()) -> list[str]:
    """One line per reason (in the order they first occur), each naming its
    variables: "employed_code — Nominal (categories); this role takes …"."""
    allowed_text = " / ".join(ui.t(f"level.{level}") for level in allowed)
    groups: dict[tuple[str, str], list[str]] = {}
    for item in left_out:
        groups.setdefault((item.reason, item.detail), []).append(item.name)
    lines = []
    for (reason, detail), names in groups.items():
        listed = _names_text(ui, names)
        if reason == "role":
            lines.append(ui.t("vars.why.role", names=listed, role=ui.t(f"vars.role.{detail}")))
        elif reason == "level":
            lines.append(ui.t("vars.why.level", names=listed, level=ui.t(f"level.{detail}"),
                              allowed=allowed_text))
        else:
            lines.append(ui.t(f"vars.why.{reason}", names=listed))
    return lines


# ======================================================================= controls
def _ft():
    import flet as ft

    return ft


def search_hint(ui, offered: list[str]) -> str:
    """The examples under the search field, taken from the data itself."""
    groups = name_groups(offered)
    if groups:
        stem, members = max(groups, key=lambda group: len(group[1]))
        pattern, span = group_pattern(stem), f"{members[0]}..{members[-1]}"
    elif len(offered) >= 2:
        pattern = f"{offered[0][:3]}*"
        span = f"{offered[0]}..{offered[min(len(offered), 5) - 1]}"
    else:
        pattern, span = "item*", "item1..item5"
    return ui.t("vars.search_hint", pattern=pattern, range=span)


MAX_GROUP_BUTTONS = 10
# A role that offers more variables lists, until a search, a name group or
# "Show all", only those chosen: about 100 boxes are 100 Tab stops and push
# the confirmations a screen and more down the page (review U2, §7).
LIST_LIMIT = 40


def role_panel(ui, *, key: str, title: str, offered: list[str], left_out: list[NotOffered],
               chosen: list[str], query: str, allowed: Iterable[str],
               label: Callable[[str], str], on_toggle: Callable[[str, bool], None],
               on_add: Callable[[list[str]], None], on_remove: Callable[[list[str]], None],
               on_query: Callable[[str], None], quick: list | None = None,
               order: list[str] | None = None, expanded: bool = False,
               on_expand: Callable[[bool], None] | None = None):
    """The panel of one multiple role, rebuilt on every render of its page.

    ``key`` prefixes every data key: the boxes keep ``{key}-{name}`` (the
    keys journeys and tests use), the panel's own controls ``{key}:…``
    (``:search``, ``:group:{stem}``, ``:select-shown``, ``:unselect-shown``,
    ``:show-all``, ``:count``, ``:not-offered``), which no variable name can
    produce. ``quick`` are the page's own buttons (all of a level, a task's
    variables, …), shown with the panel's actions. More than
    :data:`LIST_LIMIT` offered variables are listed only when searched for,
    or all of them when ``expanded`` (``on_expand`` switches it)."""
    import workspace_components as wc
    import workspace_tokens as tk

    ft = _ft()
    order = list(order if order is not None else offered)
    shown = filter_names(offered, query, order)
    chosen_set = set(chosen)
    # Chosen earlier but not offered now (another role took it, its level
    # changed): still listed, ticked, so that it can be unticked.
    stray = [name for name in chosen if name not in offered]
    field = wc.text_field(ui, ui.t("vars.search"), query, width=320,
                          on_change=lambda e: on_query(e.control.value or ""),
                          data=f"{key}:search")
    field.key = f"{key}:search"
    field.on_submit = lambda e: on_add(filter_names(offered, e.control.value or "", order))
    # Not a wrapping row: Flutter cannot lay out an expanding child in one.
    parts: list = [
        wc.section_label(ui, title),
        ft.Row([field, ft.Container(wc.caption(ui, search_hint(ui, offered)), expand=True)],
               spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ]
    groups = name_groups(offered)
    group_buttons = []
    for stem, members in groups[:MAX_GROUP_BUTTONS]:
        complete = all(name in chosen_set for name in members)
        pattern = group_pattern(stem)
        if complete:
            button = wc.button(ui, ui.t("vars.ungroup", pattern=pattern, count=len(members)),
                               lambda e, m=tuple(members): on_remove(list(m)), kind="quiet",
                               icon=ft.Icons.REMOVE_DONE,
                               tooltip=ui.t("vars.ungroup_tip", count=len(members)),
                               data=f"{key}:group:{stem}", key=f"{key}:group:{stem}")
        else:
            button = wc.button(ui, ui.t("vars.group", pattern=pattern, count=len(members)),
                               lambda e, m=tuple(members): on_add(list(m)), kind="quiet",
                               icon=ft.Icons.DONE_ALL,
                               tooltip=ui.t("vars.group_tip", count=len(members), stem=stem),
                               data=f"{key}:group:{stem}", key=f"{key}:group:{stem}")
        group_buttons.append(button)
    # The rows that come and go carry keys: the boxes keep their place (and
    # a box ticked with Space keeps the keyboard focus) when "Clear" or
    # "Select all shown" appears above them.
    if group_buttons:
        parts.append(ft.Row(group_buttons, wrap=True, spacing=tk.SPACE_2,
                            key=f"{key}:groups"))
    if len(groups) > MAX_GROUP_BUTTONS:
        parts.append(wc.caption(ui, ui.t("vars.more_groups",
                                         count=len(groups) - MAX_GROUP_BUTTONS)))
    actions = list(quick or [])
    long_list = len(offered) > LIST_LIMIT and on_expand is not None and not query.strip()
    collapsed = long_list and not expanded
    if long_list:
        actions.append(wc.button(
            ui, ui.t("vars.show_chosen") if expanded else ui.t("vars.show_all",
                                                                count=len(offered)),
            lambda e: on_expand(not expanded), kind="quiet",
            icon=ft.Icons.UNFOLD_LESS if expanded else ft.Icons.UNFOLD_MORE,
            data=f"{key}:show-all", key=f"{key}:show-all"))
    if query.strip():
        to_add = [name for name in shown if name not in chosen_set]
        to_remove = [name for name in shown if name in chosen_set]
        if to_add:
            actions.append(wc.button(ui, ui.t("vars.select_shown", count=len(to_add)),
                                     lambda e, n=tuple(to_add): on_add(list(n)), kind="quiet",
                                     icon=ft.Icons.PLAYLIST_ADD_CHECK,
                                     data=f"{key}:select-shown", key=f"{key}:select-shown"))
        if to_remove:
            actions.append(wc.button(ui, ui.t("vars.unselect_shown", count=len(to_remove)),
                                     lambda e, n=tuple(to_remove): on_remove(list(n)),
                                     kind="quiet", icon=ft.Icons.PLAYLIST_REMOVE,
                                     data=f"{key}:unselect-shown", key=f"{key}:unselect-shown"))
    if actions:
        parts.append(ft.Row(actions, wrap=True, spacing=tk.SPACE_2, key=f"{key}:actions"))
    total = len(offered) + len(stray)
    count = (ui.t("vars.count_shown", selected=len(chosen), total=total, shown=len(shown))
             if query.strip() else ui.t("vars.count", selected=len(chosen), total=total))
    count_text = wc.text(ui, count, tk.TYPE_LABEL, color=ui.p.text_secondary,
                         data=f"{key}:count")
    count_text.key = f"{key}:count"
    parts.append(count_text)
    visible = (chosen_set if collapsed else set(shown)) | set(stray)
    listed = [name for name in order if name in visible] \
        + [name for name in stray if name not in order]
    boxes = []
    for name in listed:
        box = wc.checkbox(ui, label(name), name in chosen_set,
                          on_change=lambda e, n=name: on_toggle(n, bool(e.control.value)),
                          data=f"{key}-{name}")
        box.key = f"{key}-{name}"
        boxes.append(box)
    if boxes:
        parts.append(ft.Container(ft.Row(boxes, wrap=True, spacing=tk.SPACE_4, run_spacing=0),
                                  data=key, key=f"{key}:boxes"))
    if collapsed:
        hidden = len([name for name in offered if name not in visible])
        parts.append(wc.caption(ui, ui.t("vars.collapsed", count=hidden),
                                data=f"{key}:collapsed"))
    elif not boxes:
        parts.append(wc.caption(ui, ui.t("vars.none_match", query=query.strip())
                                if query.strip() else ui.t("vars.none_offered"),
                                data=f"{key}:none"))
    reasons = left_out
    if query.strip():          # why a variable searched for is not listed
        names = filter_names([item.name for item in left_out], query, order)
        reasons = [item for item in left_out if item.name in set(names)]
    if reasons:
        lines = not_offered_lines(ui, reasons, allowed)
        parts.append(wc.text(ui, "\n".join([ui.t("vars.not_offered")] + ["• " + line
                                                                          for line in lines]),
                             tk.TYPE_CAPTION, color=ui.p.text_secondary,
                             data=f"{key}:not-offered"))
    return ft.Container(ft.Column(parts, spacing=tk.SPACE_2,
                                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                        key=f"{key}:panel", data=f"{key}:panel")


# ============================================ Data → Prepare: the scale's item list
class PreparationItems:
    """The item list of the hosted *Prepare data* panel (a scale score), as a
    variable panel: search, name groups, select or unselect what is shown,
    clear, a count and the reasons for what is not offered.

    The hosted panel is built once and updated in place (``page.update()``,
    not the workspace's keyed re-render), so this list keeps its controls
    and changes what they show: a control rebuilt in that kind of update is
    a new widget, and the search field would lose the keyboard focus at
    every character typed. Its boxes are named by the column alone, as in
    the classic list, and :meth:`selected` reads them, so code that ticks a
    box directly still gives the items scored (``preparation_ui`` reads the
    selection on Apply). Identifiers and variables confirmed as nominal are
    not offered, with the reason shown (D7); the working copy's new columns
    are."""

    KEY = "prep-items"

    def __init__(self, app):
        ft = _ft()
        self.app = app
        self.names: list[str] = []
        self.left_out: list[NotOffered] = []
        self.query = ""
        self.boxes: dict = {}
        self.control = ft.Column(spacing=8, data=f"{self.KEY}:panel")
        self._look = None          # the language and palette its controls were made for

    # ------------------------------------------------ preparation_ui's contract
    def set_columns(self, frame) -> None:
        """A new working copy: its numeric columns, nothing ticked, no search."""
        import pandas as pd

        ft = _ft()
        session = self.app.session
        names, left_out = [], []
        for column in (str(c) for c in frame.columns):
            info = session.variables.get(column)
            if not pd.api.types.is_numeric_dtype(frame[column]):
                left_out.append(NotOffered(column, "not_numeric"))
            elif info is not None and (info.suggested == "id" or info.confirmed == "id"):
                left_out.append(NotOffered(column, "identifier"))
            elif info is not None and info.confirmed == "nominal":
                left_out.append(NotOffered(column, "level", "nominal"))
            else:
                names.append(column)
        self.names, self.left_out, self.query = names, left_out, ""
        self.boxes = {}
        for name in names:
            box = ft.Checkbox(label=name, value=False, data=f"{self.KEY}-{name}",
                              on_change=self._ticked)
            box.key = f"{self.KEY}-{name}"
            self.boxes[name] = box
        if self._look is not None:
            self.field.value = ""
        self._build()

    def selected(self) -> list[str]:
        return [name for name in self.names if bool(self.boxes[name].value)]

    def refresh(self) -> None:
        """After a change of language or theme: the controls made again in
        it (what is ticked and searched stays)."""
        if self._look != self._current_look():
            self._build()
            self._update()

    # --------------------------------------------------------------- actions
    def _ticked(self, e=None) -> None:
        self._build()
        self._update()

    def _set(self, names, value: bool) -> None:
        for name in names:
            if name in self.boxes:
                self.boxes[name].value = value
        self._build()
        self._update()

    def _search(self, e) -> None:
        self.query = e.control.value or ""
        self._build()
        self._update()

    def _update(self) -> None:
        try:
            self.app.page.update()
        except Exception:      # not on a page yet (built before it is shown)
            pass

    # ---------------------------------------------------------------- layout
    def _current_look(self):
        ui = self.app.ui
        return ui.language, ui.p

    def _make(self) -> None:
        """The lasting controls, in the language and palette on screen."""
        import workspace_components as wc
        import workspace_tokens as tk

        ft = _ft()
        ui, key = self.app.ui, self.KEY
        self.field = wc.text_field(ui, ui.t("vars.search"), self.query, width=300,
                                   on_change=self._search, data=f"{key}:search")
        self.field.key = f"{key}:search"
        self.field.on_submit = lambda e: self._set(
            filter_names(self.names, e.control.value or "", self.names), True)
        self.hint = wc.caption(ui, "")
        self.actions = ft.Row(wrap=True, spacing=tk.SPACE_2)
        self.count = wc.text(ui, "", tk.TYPE_LABEL, color=ui.p.text_secondary,
                             data=f"{key}:count")
        # Its own scrolling list, as the classic one (170 px there).
        self.list = ft.Column(height=220, scroll=ft.ScrollMode.AUTO, spacing=0,
                              data=f"{key}:list")
        self.none = wc.caption(ui, "", data=f"{key}:none")
        self.body = ft.Column(spacing=0)
        self.reasons_text = wc.text(ui, "", tk.TYPE_CAPTION, color=ui.p.text_secondary,
                                    data=f"{key}:not-offered")
        self.reasons = ft.Column(spacing=0)
        self.control.controls = [
            ft.Row([self.field, ft.Container(self.hint, expand=True)],     # no wrap: it expands
                   spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.actions, self.count, self.body, self.reasons]
        self._look = self._current_look()

    def _build(self) -> None:
        import workspace_components as wc

        ft = _ft()
        if self._look != self._current_look():
            self._make()
        ui, key = self.app.ui, self.KEY
        chosen = self.selected()
        chosen_set = set(chosen)
        query = self.query.strip()
        shown = filter_names(self.names, self.query, self.names)
        self.hint.value = search_hint(ui, self.names)
        buttons = []
        for stem, members in name_groups(self.names)[:MAX_GROUP_BUTTONS]:
            pattern = group_pattern(stem)
            if all(name in chosen_set for name in members):
                buttons.append(wc.button(
                    ui, ui.t("vars.ungroup", pattern=pattern, count=len(members)),
                    lambda e, m=tuple(members): self._set(m, False), kind="quiet",
                    icon=ft.Icons.REMOVE_DONE, tooltip=ui.t("vars.ungroup_tip",
                                                            count=len(members)),
                    data=f"{key}:group:{stem}", key=f"{key}:group:{stem}"))
            else:
                buttons.append(wc.button(
                    ui, ui.t("vars.group", pattern=pattern, count=len(members)),
                    lambda e, m=tuple(members): self._set(m, True), kind="quiet",
                    icon=ft.Icons.DONE_ALL,
                    tooltip=ui.t("vars.group_tip", count=len(members), stem=stem),
                    data=f"{key}:group:{stem}", key=f"{key}:group:{stem}"))
        if query:
            to_add = [name for name in shown if name not in chosen_set]
            to_remove = [name for name in shown if name in chosen_set]
            if to_add:
                buttons.append(wc.button(ui, ui.t("vars.select_shown", count=len(to_add)),
                                         lambda e, n=tuple(to_add): self._set(n, True),
                                         kind="quiet", icon=ft.Icons.PLAYLIST_ADD_CHECK,
                                         data=f"{key}:select-shown",
                                         key=f"{key}:select-shown"))
            if to_remove:
                buttons.append(wc.button(ui, ui.t("vars.unselect_shown", count=len(to_remove)),
                                         lambda e, n=tuple(to_remove): self._set(n, False),
                                         kind="quiet", icon=ft.Icons.PLAYLIST_REMOVE,
                                         data=f"{key}:unselect-shown",
                                         key=f"{key}:unselect-shown"))
        if chosen:
            buttons.append(wc.button(ui, ui.t("pick.clear"),
                                     lambda e: self._set(list(self.names), False), kind="quiet",
                                     icon=ft.Icons.CLEAR, data=f"{key}:clear",
                                     key=f"{key}:clear"))
        self.actions.controls = buttons
        self.count.value = (ui.t("vars.count_shown", selected=len(chosen), total=len(self.names),
                                 shown=len(shown)) if query
                            else ui.t("vars.count", selected=len(chosen), total=len(self.names)))
        boxes = [self.boxes[name] for name in shown]
        self.list.controls = boxes
        self.none.value = (ui.t("vars.none_match", query=query) if query
                           else ui.t("vars.none_offered"))
        self.body.controls = [self.list] if boxes else [self.none]
        reasons = self.left_out
        if query:
            names = set(filter_names([item.name for item in self.left_out], self.query))
            reasons = [item for item in self.left_out if item.name in names]
        lines = not_offered_lines(ui, reasons, ("ordinal", "scale")) if reasons else []
        wc.set_text(self.reasons_text, "\n".join([ui.t("vars.not_offered")]
                                                  + ["• " + line for line in lines]))
        self.reasons.controls = [self.reasons_text] if reasons else []
