"""Flet split-screen spatial review for the scientific questionnaire importer.

Left: the rendered source page with zoom-safe overlays positioned from
normalized OCR/text-layer boxes. Right: per-question OCR confidence (raw
engine scores) kept apart from the structural heuristic, region tools
(adjust, split, merge, link, unlink, revert), a review queue and an editable
matrix grid. Nothing here modifies the source document, publishes a survey
or approves scoring.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Awaitable, Callable

import flet as ft

from matrix_reconstruction import (
    MatrixProposal, accept_cell, add_column, add_row, delete_column,
    delete_row, matrix_to_questions, move_column, move_row, set_cell,
    set_column, set_row, verify_matrix,
)
from ocr_layout import (
    OCR_CATEGORY_LABELS, OCR_HIGH_THRESHOLD, OCR_REVIEW_THRESHOLD,
    PSYCHOMETRIC_NOTICE, SpatialEvidence, assess_structure, link_line,
    merge_regions, question_ref, revert_links, review_queue, set_region_box,
    split_region, to_pixels, unlink_region,
)

BASE_VIEW_WIDTH = 560
CATEGORY_COLORS = {
    "high": "#2E7D32", "review": "#B26A00", "low": "#C62828", "unknown": "#607087",
}
SELECTED_COLOR = "#1565C0"
UNLINKED_COLOR = "#7B1FA2"
CELL_COLORS = {"missing": "#C62828", "ambiguous": "#B26A00"}


def png_size(data: bytes) -> tuple[int, int]:
    """Pixel size from a PNG header (no decoding)."""
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return (1, 1)
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _alpha(color: str, alpha: str = "33") -> str:
    return "#" + alpha + color.lstrip("#")


class SpatialReviewController:
    """Owns the overlay viewer, confidence/region panel, queue and matrix editor."""

    def __init__(
        self, page, image: ft.Image, *,
        get_review: Callable[[], object | None],
        set_review: Callable[[object], None],
        get_instrument: Callable[[], int | None],
        focus_question: Callable[[int], Awaitable[None] | None],
        render_page: Callable[[int, int], Awaitable[bytes | None]],
        page_count: Callable[[], int],
        set_page_value: Callable[[int], None],
        on_invalidate: Callable[[str], None],
        on_matrix_commit: Callable[[list[dict], str], bool],
    ):
        self.page = page
        self.image = image
        self.get_review = get_review
        self.set_review = set_review
        self.get_instrument = get_instrument
        self.focus_question_cb = focus_question
        self.render_page_cb = render_page
        self.page_count = page_count
        self.set_page_value = set_page_value
        self.on_invalidate = on_invalidate
        self.on_matrix_commit = on_matrix_commit
        self.current_page = 1
        self.pixel_size = (1, 1)
        self.selected_index: int | None = None
        self.selected_region: str | None = None
        self.matrix_index: int | None = None

        image.fit = ft.BoxFit.FILL
        self.stack = ft.Stack(controls=[image], width=BASE_VIEW_WIDTH, height=720)
        self.viewer = ft.Container(
            height=640, border=ft.Border.all(1, "#D7E1EE"), bgcolor="#F5F7FA",
            content=ft.Column(
                controls=[ft.Row(controls=[self.stack], scroll=ft.ScrollMode.AUTO)],
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        self.zoom = ft.Slider(
            min=50, max=300, divisions=25, value=100, label="{value}%", width=230,
            on_change=self._on_zoom,
        )
        self.zoom_label = ft.Text("Zoom 100 %", size=12)
        self.rotation = ft.Dropdown(
            label="Page view rotation", width=200, value="0",
            options=[ft.DropdownOption(key=str(r), text=f"{r}° clockwise") for r in (0, 90, 180, 270)],
            on_select=self._on_rotation,
        )
        self.show_unlinked = ft.Checkbox(
            label="Show unlinked text lines", value=True, on_change=self._on_toggle,
        )
        self.link_mode = ft.Checkbox(
            label="Link mode: clicking unlinked text attaches it to the selected question",
            value=False,
        )
        self.overlay_status = ft.Text("", size=12, selectable=True, color="#536781")
        self.legend = ft.Row(
            wrap=True, spacing=8,
            controls=[self._chip(SELECTED_COLOR, "Selected question")] + [
                self._chip(CATEGORY_COLORS[k], OCR_CATEGORY_LABELS[k])
                for k in ("high", "review", "low", "unknown")
            ] + [self._chip(UNLINKED_COLOR, "Unlinked text (never auto-converted)")],
        )
        # Right side: confidence + structure + region tools.
        self.ocr_confidence = ft.Text("", size=12, selectable=True)
        self.structure_status = ft.Text("", size=12, selectable=True)
        self.psychometric_notice = ft.Text(PSYCHOMETRIC_NOTICE, size=11, color="#936022")
        self.region_picker = ft.Dropdown(
            label="Linked source region", width=300, options=[], on_select=self._on_region_select,
        )
        self.box_fields = [
            ft.TextField(label=name, width=92, dense=True)
            for name in ("Left %", "Top %", "Right %", "Bottom %")
        ]
        self.apply_box = ft.Button("Apply region box", on_click=self._apply_box)
        self.split_button = ft.Button("Split region", on_click=self._split)
        self.merge_button = ft.Button("Merge this question's regions", on_click=self._merge)
        self.unlink_button = ft.Button("Unlink region", on_click=self._unlink)
        self.revert_button = ft.Button("Revert this question's regions", on_click=self._revert_one)
        self.revert_all_button = ft.Button("Revert all regions", on_click=self._revert_all)
        self.region_status = ft.Text("", size=12, selectable=True)
        self.queue_filter = ft.Dropdown(
            label="Review queue filter", width=300, value="attention",
            options=[
                ft.DropdownOption(key="attention", text="Needs attention (all flags)"),
                ft.DropdownOption(key="low_unknown", text="Low or unknown OCR confidence"),
                ft.DropdownOption(key="unlinked", text="No source region linked"),
                ft.DropdownOption(key="structure", text="Structural heuristic flags"),
            ],
            on_select=self._on_queue_filter,
        )
        self.queue_list = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=170)
        self.question_panel = ft.Column(
            spacing=8, visible=False,
            controls=[
                ft.Text("CONFIDENCE · selected question", weight="bold", size=13),
                self.ocr_confidence, self.structure_status, self.psychometric_notice,
                ft.Text("SOURCE REGIONS · manual corrections", weight="bold", size=13),
                self.region_picker,
                ft.Row(controls=self.box_fields, wrap=True, spacing=6),
                ft.Row(controls=[self.apply_box, self.split_button, self.merge_button],
                       wrap=True, spacing=8),
                ft.Row(controls=[self.unlink_button, self.revert_button, self.revert_all_button],
                       wrap=True, spacing=8),
                self.link_mode, self.region_status,
            ],
        )
        self.queue_panel = ft.Column(
            spacing=6, visible=False,
            controls=[
                ft.Text("REVIEW QUEUE · suspicious or unresolved items", weight="bold", size=13),
                self.queue_filter, self.queue_list,
            ],
        )
        self.matrix = MatrixEditor(self)
        self.left_tools = ft.Column(
            spacing=8,
            controls=[
                ft.Row(controls=[self.zoom_label, self.zoom, self.rotation], wrap=True, spacing=10),
                self.show_unlinked, self.legend, self.overlay_status,
            ],
        )

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _chip(color, label):
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            border=ft.Border.all(2, color), bgcolor=_alpha(color, "22"),
            content=ft.Text(label, size=11, color="#263748"),
        )

    @property
    def evidence(self) -> SpatialEvidence | None:
        review = self.get_review()
        return getattr(review, "spatial", None) if review is not None else None

    def _ref(self, index: int | None = None) -> str | None:
        instrument = self.get_instrument()
        index = self.selected_index if index is None else index
        if instrument is None or index is None:
            return None
        return question_ref(instrument, index)

    def _store(self, evidence: SpatialEvidence, message: str):
        review = self.get_review()
        self.set_review(replace(review, spatial=evidence))
        self.on_invalidate(message)

    def _update(self):
        try:
            self.page.update()
        except Exception:
            pass

    @property
    def view_rotation(self) -> int:
        try:
            return int(self.rotation.value or 0)
        except ValueError:
            return 0

    # ------------------------------------------------------------ viewing
    def reset(self):
        self.selected_index = None
        self.selected_region = None
        self.current_page = 1
        self.rotation.value = "0"
        self.zoom.value = 100
        self.zoom_label.value = "Zoom 100 %"
        self.question_panel.visible = False
        self.queue_panel.visible = False
        self.matrix.reset()
        self.stack.controls = [self.image]

    def display_size(self) -> tuple[float, float]:
        width = BASE_VIEW_WIDTH * float(self.zoom.value or 100) / 100
        px_w, px_h = self.pixel_size
        return width, width * px_h / max(px_w, 1)

    def show_rendered(self, page_number: int, png: bytes):
        """Called after the host rendered a page; lays out overlays."""
        self.current_page = page_number
        self.pixel_size = png_size(png)
        self.relayout()

    def relayout(self):
        width, height = self.display_size()
        self.image.width, self.image.height = width, height
        self.stack.width, self.stack.height = width, height
        overlays = self._overlays(width, height)
        self.stack.controls = [self.image, *overlays]
        self.refresh_panels()

    def _page_layout(self):
        evidence = self.evidence
        if evidence is None:
            return None, "No spatial data: run local OCR or import a text-based PDF."
        layout = evidence.page(self.current_page)
        if layout is None:
            return None, f"No positioned text for page {self.current_page}."
        if not layout.has_geometry:
            return None, "This recognizer returned text without coordinates; no overlay."
        if layout.rotation != self.view_rotation:
            return None, (
                f"Overlay hidden: text positions were recorded at {layout.rotation}° "
                f"view rotation. Switch back or re-run OCR at {self.view_rotation}°."
            )
        return layout, ""

    def _overlays(self, width, height) -> list[ft.Control]:
        layout, reason = self._page_layout()
        if layout is None:
            self.overlay_status.value = reason
            return []
        evidence = self.evidence
        controls = []
        selected = self._ref()
        regions = evidence.regions_on_page(self.current_page)
        for ref, region in regions:
            conf = evidence.confidence(ref)
            is_selected = ref == selected
            color = SELECTED_COLOR if is_selected else CATEGORY_COLORS[conf.category]
            left, top, w, h = to_pixels(region.box, width, height)
            controls.append(ft.Container(
                left=left, top=top, width=max(w, 2), height=max(h, 2),
                border=ft.Border.all(3 if region.id == self.selected_region else (2 if is_selected else 1), color),
                bgcolor=_alpha(color, "30" if is_selected else "18"),
                tooltip=f"Question {ref.split(':')[1]}: {conf.label} · region {region.id} ({region.origin})",
                data=("region", ref, region.id),
                on_click=self._region_click_handler(ref, region.id),
            ))
        unlinked = evidence.unlinked_lines(self.current_page)
        if self.show_unlinked.value:
            for line in unlinked:
                left, top, w, h = to_pixels(line.box, width, height)
                controls.append(ft.Container(
                    left=left, top=top, width=max(w, 2), height=max(h, 2),
                    border=ft.Border.all(1, UNLINKED_COLOR), bgcolor=_alpha(UNLINKED_COLOR, "10"),
                    tooltip="Unlinked text: " + line.text[:120],
                    data=("line", line.id),
                    on_click=self._line_click_handler(line.id),
                ))
        controls.extend(self.matrix.cell_overlays(self.current_page, width, height))
        source = {"tesseract_tsv": "local OCR", "pdf_text_layer": "PDF text layer"}.get(layout.source, layout.source)
        self.overlay_status.value = (
            f"Page {self.current_page}: {len(regions)} linked region(s), "
            f"{len(unlinked)} unlinked line(s) · positions from {source}. "
            "Click a box to select its question; overlays follow zoom."
        )
        return controls

    def _region_click_handler(self, ref, region_id):
        async def handler(event=None):
            await self.select_region(ref, region_id)
        return handler

    def _line_click_handler(self, line_id):
        def handler(event=None):
            self.click_unlinked(line_id)
        return handler

    async def select_region(self, ref: str, region_id: str | None):
        instrument, index = (int(x) for x in ref.split(":"))
        if instrument != self.get_instrument():
            return
        self.selected_index = index
        self.selected_region = region_id
        result = self.focus_question_cb(index)
        if asyncio.iscoroutine(result):
            await result
        self.relayout()
        self._update()

    def click_unlinked(self, line_id: str):
        evidence = self.evidence
        layout = evidence.page(self.current_page) if evidence else None
        line = layout.line(line_id) if layout else None
        if line is None:
            return
        ref = self._ref()
        if self.link_mode.value and ref is not None:
            try:
                updated = link_line(evidence, ref, self.current_page, line_id)
            except (KeyError, ValueError) as error:
                self.region_status.value = f"Link rejected: {error}"
            else:
                self.selected_region = updated.regions(ref)[-1].id
                self._store(updated, "Source region linked manually; approvals reset.")
                self.region_status.value = f"Linked “{line.text[:60]}” to question {self.selected_index + 1}."
        else:
            self.region_status.value = (
                f"Unlinked text: “{line.text[:100]}”. No question was created. "
                "Enable link mode to attach it to the selected question."
            )
        self.relayout()
        self._update()

    async def go_to_page(self, number: int):
        if number == self.current_page and self.image.src:
            self.relayout()
            return
        self.set_page_value(number)
        png = await self.render_page_cb(number, self.view_rotation)
        if png:
            self.show_rendered(number, png)

    async def on_question_selected(self, index: int | None):
        """Host selected a question in its picker: keep the page in sync."""
        self.selected_index = index
        ref = self._ref()
        regions = self.evidence.regions(ref) if (self.evidence and ref) else ()
        self.selected_region = regions[0].id if regions else None
        target = regions[0].page if regions else None
        if target is None and index is not None:
            review, instrument = self.get_review(), self.get_instrument()
            try:
                target = review.instruments[instrument].questions[index].page
            except (AttributeError, IndexError, TypeError):
                target = None
        if target is not None and 1 <= target <= self.page_count() and target != self.current_page:
            await self.go_to_page(target)
        else:
            self.relayout()

    def _on_zoom(self, event=None):
        self.zoom_label.value = f"Zoom {int(self.zoom.value)} %"
        self.relayout()
        self._update()

    async def _on_rotation(self, event=None):
        png = await self.render_page_cb(self.current_page, self.view_rotation)
        if png:
            self.show_rendered(self.current_page, png)
        self._update()

    def _on_toggle(self, event=None):
        self.relayout()
        self._update()

    # ------------------------------------------------------------- panels
    def refresh_panels(self):
        review = self.get_review()
        instrument = self.get_instrument()
        has_review = review is not None and instrument is not None
        self.queue_panel.visible = has_review
        self.question_panel.visible = has_review and self.selected_index is not None
        if has_review:
            self._refresh_queue()
        self.matrix.refresh()
        if not self.question_panel.visible:
            return
        evidence = self.evidence
        ref = self._ref()
        candidate = review.instruments[instrument].questions[self.selected_index] \
            if self.selected_index < len(review.instruments[instrument].questions) else None
        if candidate is None:
            self.question_panel.visible = False
            return
        regions = evidence.regions(ref) if evidence else ()
        if evidence is None:
            self.ocr_confidence.value = (
                "OCR confidence: unknown — no OCR word scores (text-based source or no OCR run)."
            )
        else:
            conf = evidence.confidence(ref)
            self.ocr_confidence.value = "OCR confidence (raw Tesseract word scores): " + conf.describe()
            self.ocr_confidence.color = CATEGORY_COLORS[conf.category]
        expected = None
        if self.selected_index:
            expected = review.instruments[instrument].questions[self.selected_index - 1].number + 1
        elif candidate is not None:
            expected = 1
        structure = assess_structure(
            candidate, expected_number=expected,
            linked_regions=len(regions) if evidence is not None else None,
        )
        self.structure_status.value = (
            f"{structure.label}: " + ("; ".join(structure.reasons) or "no reconstruction flags.")
            + " This is a rule-based check, not a percentage or a calibrated probability."
        )
        self.region_picker.options = [
            ft.DropdownOption(key=r.id, text=f"{r.id} · page {r.page} · {r.origin}") for r in regions
        ]
        if self.selected_region not in {r.id for r in regions}:
            self.selected_region = regions[0].id if regions else None
        self.region_picker.value = self.selected_region
        region = next((r for r in regions if r.id == self.selected_region), None)
        for field, value in zip(self.box_fields, region.box if region else (None,) * 4):
            field.value = "" if value is None else f"{value * 100:.1f}"
        for control in (self.apply_box, self.split_button, self.unlink_button):
            control.disabled = region is None
        self.merge_button.disabled = len(regions) < 2
        self.revert_all_button.disabled = evidence is None
        self.revert_button.disabled = evidence is None

    def _refresh_queue(self):
        review = self.get_review()
        instrument = self.get_instrument()
        evidence = self.evidence
        mode = self.queue_filter.value or "attention"
        include = {
            "attention": ("low", "unknown", "review", "unlinked"),
            "low_unknown": ("low", "unknown"),
            "unlinked": ("unlinked",),
            "structure": (),
        }[mode]
        entries = []
        if mode == "structure":
            for j, candidate in enumerate(review.instruments[instrument].questions):
                ref = question_ref(instrument, j)
                linked = len(evidence.regions(ref)) if evidence else None
                expected = review.instruments[instrument].questions[j-1].number + 1 if j else 1
                result = assess_structure(candidate, expected_number=expected, linked_regions=linked)
                if result.category != "consistent":
                    entries.append((j, result.label))
        else:
            for ref, reason in review_queue(review, evidence, include=include):
                i, j = (int(x) for x in ref.split(":"))
                if i == instrument:
                    entries.append((j, OCR_CATEGORY_LABELS.get(reason, "No source region linked")))
        questions = review.instruments[instrument].questions
        self.queue_list.controls = [
            ft.TextButton(
                content=f"{questions[j].number}. {questions[j].question['prompt'][:48]} — {label}",
                on_click=self._queue_handler(j),
            )
            for j, label in entries[:200]
        ] or [ft.Text("No items match this filter.", size=12, color="#607087")]
        unresolved = sum(len(m.unresolved_cells) for m in getattr(review, "matrices", ()))
        if unresolved:
            self.queue_list.controls.append(ft.Text(
                f"Matrix: {unresolved} missing/ambiguous cell(s) — see the matrix editor.",
                size=12, color=CELL_COLORS["missing"],
            ))

    def _queue_handler(self, index):
        async def handler(event=None):
            self.selected_index = index
            result = self.focus_question_cb(index)
            if asyncio.iscoroutine(result):
                await result
            await self.on_question_selected(index)
            self._update()
        return handler

    def _on_queue_filter(self, event=None):
        self.refresh_panels()
        self._update()

    def _on_region_select(self, event=None):
        self.selected_region = self.region_picker.value
        self.relayout()
        self._update()

    # ------------------------------------------------------- region edits
    def _edit(self, operation, success: str):
        ref = self._ref()
        evidence = self.evidence
        if ref is None or evidence is None:
            self.region_status.value = "Select a question with spatial data first."
            self._update()
            return
        try:
            updated = operation(evidence, ref)
        except (KeyError, ValueError, IndexError) as error:
            self.region_status.value = f"Region change rejected: {error}"
        else:
            regions = updated.regions(ref)
            if self.selected_region not in {r.id for r in regions}:
                self.selected_region = regions[-1].id if regions else None
            self._store(updated, "Source regions changed; approvals reset.")
            self.region_status.value = success + " The source document is unchanged."
        self.relayout()
        self._update()

    def _apply_box(self, event=None):
        try:
            box = [float((f.value or "").replace(",", ".")) / 100 for f in self.box_fields]
        except ValueError:
            self.region_status.value = "Enter four numeric percentages (0–100)."
            self._update()
            return
        region = self.selected_region
        self._edit(lambda e, r: set_region_box(e, r, region, box), "Region box adjusted.")

    def _split(self, event=None):
        region = self.selected_region
        self._edit(lambda e, r: split_region(e, r, region), "Region split in two.")

    def _merge(self, event=None):
        self._edit(lambda e, r: merge_regions(e, r, [x.id for x in e.regions(r)]),
                   "Regions merged.")

    def _unlink(self, event=None):
        region = self.selected_region
        self._edit(lambda e, r: unlink_region(e, r, region), "Region unlinked.")

    def _revert_one(self, event=None):
        self._edit(lambda e, r: revert_links(e, r), "Detected regions restored for this question.")

    def _revert_all(self, event=None):
        self._edit(lambda e, r: revert_links(e), "All detected regions restored.")


class MatrixEditor:
    """Editable grid for a :class:`MatrixProposal` with explicit verification."""

    def __init__(self, owner: SpatialReviewController):
        self.owner = owner
        self.picker = ft.Dropdown(
            label="Detected response matrix", width=420, options=[],
            on_select=self._on_pick,
        )
        self.status = ft.Text("", size=12, selectable=True)
        self.issues = ft.Column(spacing=3)
        self.grid = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
        self.grid_frame = ft.Container(
            content=ft.Row(controls=[self.grid], scroll=ft.ScrollMode.AUTO),
            border=ft.Border.all(1, "#D7E1EE"), padding=8,
        )
        self.original = ft.Text("", size=11, selectable=True, font_family="monospace")
        self.apply_button = ft.Button("Apply grid edits", on_click=self._apply)
        self.add_row_button = ft.Button("Add row", on_click=self._add_row)
        self.add_column_button = ft.Button("Add column", on_click=self._add_column)
        self.accept_button = ft.Button("Accept flagged cells as shown", on_click=self._accept_flagged)
        self.verify_button = ft.Button("Verify grid against source", on_click=self._verify)
        self.codes_confirm = ft.Checkbox(
            label="Apply printed numeric codes as scale values (reviewed by researcher)", value=False,
        )
        self.reverse_confirm = ft.Checkbox(
            label="Apply marked reverse-keyed rows (reviewed by researcher)", value=False,
        )
        self.commit_button = ft.Button("Use verified matrix rows as editable draft", disabled=True,
                                       on_click=self._commit)
        self.highlight = ft.Checkbox(
            label="Highlight missing/ambiguous matrix cells on the page", value=True,
            on_change=lambda e: (self.owner.relayout(), self.owner._update()),
        )
        self.fields: dict = {}
        # The proposal object the grid fields and scoring confirmations
        # belong to. View-only refreshes (zoom, page, selection) keep both;
        # any other proposal (new document, OCR run, edit, verify, another
        # matrix) rebuilds the grid and clears the scoring confirmations.
        self._rendered: MatrixProposal | None = None
        self.panel = ft.ExpansionTile(
            title=ft.Text("MATRIX EDITOR · row/column rating scales"),
            expanded=False, visible=False,
            controls=[
                ft.Text(
                    "Each row becomes a question sharing one response scale. Visual "
                    "column order never implies scoring: verify the grid, then "
                    "separately confirm numeric codes and reverse-keyed rows.",
                    size=12,
                ),
                self.picker, self.status, self.issues, self.highlight,
                ft.Row(controls=[self.apply_button, self.add_row_button, self.add_column_button,
                                 self.accept_button], wrap=True, spacing=8),
                self.grid_frame,
                ft.ExpansionTile(
                    title=ft.Text("Original detected grid (read-only provenance)"),
                    expanded=False, controls=[self.original],
                ),
                self.verify_button, self.codes_confirm, self.reverse_confirm,
                self.commit_button,
            ],
        )

    # -------------------------------------------------------------- state
    def matrices(self) -> tuple[MatrixProposal, ...]:
        review = self.owner.get_review()
        return tuple(getattr(review, "matrices", ()) or ()) if review is not None else ()

    def current(self) -> MatrixProposal | None:
        found = self.matrices()
        index = self.owner.matrix_index
        if index is None or not 0 <= index < len(found):
            return None
        return found[index]

    def store(self, proposal: MatrixProposal, message: str):
        review = self.owner.get_review()
        found = list(self.matrices())
        found[self.owner.matrix_index] = proposal
        self.owner.set_review(replace(review, matrices=tuple(found)))
        self.codes_confirm.value = False
        self.reverse_confirm.value = False
        self.owner.on_invalidate(message)

    def clear_confirmations(self):
        self.codes_confirm.value = False
        self.reverse_confirm.value = False

    def reset(self):
        self.owner.matrix_index = None
        self.panel.visible = False
        self.grid.controls = []
        self.fields = {}
        self._rendered = None
        self.clear_confirmations()

    def refresh(self):
        found = self.matrices()
        self.panel.visible = bool(found)
        if not found:
            self.owner.matrix_index = None
            if self._rendered is not None:
                self._rendered = None
                self.clear_confirmations()
            return
        if self.owner.matrix_index is None or self.owner.matrix_index >= len(found):
            self.owner.matrix_index = 0
        self.picker.options = [
            ft.DropdownOption(
                key=str(k),
                text=f"{m.title[:40]} · {len(m.rows)} rows × {len(m.columns)} columns · "
                     f"{'/'.join(map(str, m.pages))} ({m.source_kind})",
            ) for k, m in enumerate(found)
        ]
        self.picker.value = str(self.owner.matrix_index)
        matrix = self.current()
        if matrix is self._rendered:
            return  # view-only refresh: keep typed-but-unapplied edits
        self.clear_confirmations()
        self._rendered = matrix
        self._render(matrix)

    def _render(self, matrix: MatrixProposal):
        problems = matrix.blocking_problems()
        self.status.value = (
            ("VERIFIED grid mapping. " if matrix.verified else "NOT verified. ")
            + f"{len(matrix.unresolved_cells)} unresolved cell(s). "
            + ("Edited manually. " if matrix.edited else "")
            + "Codes: " + (", ".join(c or "—" for c in matrix.codes))
        )
        self.issues.controls = [
            ft.Text("Review: " + issue, size=11, color="#936022", selectable=True)
            for issue in matrix.issues
        ] + [
            ft.Text("Blocking: " + problem, size=11, color=CELL_COLORS["missing"], selectable=True)
            for problem in problems
        ]
        self.original.value = "\n".join(" | ".join(row) for row in matrix.source_grid)[:20000]
        self.verify_button.disabled = bool(problems) or matrix.verified
        self.commit_button.disabled = not matrix.verified
        self.codes_confirm.disabled = any(code is None for code in matrix.codes)
        if self.codes_confirm.disabled:
            self.codes_confirm.value = False
        self.reverse_confirm.disabled = not any(r.reverse_proposed for r in matrix.rows)
        if self.reverse_confirm.disabled:
            self.reverse_confirm.value = False
        self.fields = {"labels": [], "codes": [], "numbers": [], "prompts": [], "cells": [], "reverse": []}
        header = [ft.Container(width=56), ft.Container(width=300, content=ft.Text("Question text", weight="bold", size=12))]
        codes_row = [ft.Container(width=56), ft.Container(width=300, content=ft.Text("Numeric code", size=12))]
        for c, column in enumerate(matrix.columns):
            label = ft.TextField(value=column.label, width=118, dense=True, text_size=12,
                                 hint_text="label", tooltip=column.group or None,
                                 border_color=CELL_COLORS["ambiguous"] if column.ambiguous else None)
            code = ft.TextField(value=column.code or "", width=118, dense=True, text_size=12, hint_text="code")
            self.fields["labels"].append(label)
            self.fields["codes"].append(code)
            header.append(ft.Column(spacing=2, controls=[
                label,
                ft.Row(spacing=0, controls=[
                    ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Move column left", icon_size=16,
                                  on_click=self._column_op(c, "left")),
                    ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Move column right", icon_size=16,
                                  on_click=self._column_op(c, "right")),
                    ft.IconButton(ft.Icons.CLOSE, tooltip="Delete column", icon_size=16,
                                  on_click=self._column_op(c, "delete")),
                ]),
            ]))
            codes_row.append(code)
        header.append(ft.Text("Rev.", size=12, tooltip="Proposed reverse-keyed row"))
        rows = [ft.Row(controls=header, spacing=6), ft.Row(controls=codes_row, spacing=6)]
        for r, row in enumerate(matrix.rows):
            number = ft.TextField(value="" if row.number is None else str(row.number), width=56,
                                  dense=True, text_size=12, hint_text="#")
            prompt = ft.TextField(value=row.prompt, width=300, dense=True, text_size=12,
                                  multiline=True, min_lines=1, max_lines=3,
                                  tooltip=row.provenance)
            cells = []
            for c, cell in enumerate(row.cells):
                color = CELL_COLORS.get(cell.state)
                cells.append(ft.TextField(
                    value=cell.text, width=118, dense=True, text_size=12,
                    hint_text=cell.state, border_color=color,
                    tooltip=f"{cell.state} · {cell.provenance}",
                ))
            reverse = ft.Checkbox(value=row.reverse_proposed, tooltip="Reverse-key mark (proposal only)")
            self.fields["numbers"].append(number)
            self.fields["prompts"].append(prompt)
            self.fields["cells"].append(cells)
            self.fields["reverse"].append(reverse)
            rows.append(ft.Row(spacing=6, controls=[
                number, prompt, *cells, reverse,
                ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Move row up", icon_size=16,
                              on_click=self._row_op(r, "up")),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, tooltip="Move row down", icon_size=16,
                              on_click=self._row_op(r, "down")),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Delete row", icon_size=16,
                              on_click=self._row_op(r, "delete")),
            ]))
        self.grid.controls = rows

    def cell_overlays(self, page_number: int, width: float, height: float) -> list[ft.Control]:
        matrix = self.current()
        if matrix is None or not self.highlight.value or matrix.source_kind == "docx_table":
            return []
        out = []
        for r, c in matrix.unresolved_cells:
            row = matrix.rows[r]
            cell = row.cells[c]
            if row.page != page_number or cell.box is None:
                continue
            left, top, w, h = to_pixels(cell.box, width, height)
            color = CELL_COLORS[cell.state]
            out.append(ft.Container(
                left=left, top=top, width=max(w, 6), height=max(h, 6),
                border=ft.Border.all(2, color), bgcolor=_alpha(color, "26"),
                tooltip=f"Matrix row {r+1}, column {c+1}: {cell.state} “{cell.text}”",
                data=("cell", r, c),
            ))
        return out

    # ------------------------------------------------------------ actions
    def _collect(self, matrix: MatrixProposal) -> MatrixProposal:
        """Apply every changed text field to the proposal (atomic)."""
        f = self.fields
        if not f or len(f["prompts"]) != len(matrix.rows) or len(f["labels"]) != len(matrix.columns):
            return matrix
        out = matrix
        for c, column in enumerate(matrix.columns):
            label, code = f["labels"][c].value or "", (f["codes"][c].value or "").strip()
            if label.strip() != column.label or (code or None) != column.code:
                out = set_column(out, c, label=label, code=code or None)
        for r, row in enumerate(matrix.rows):
            raw_number = (f["numbers"][r].value or "").strip()
            number = int(raw_number) if raw_number else None
            prompt = f["prompts"][r].value or ""
            reverse = bool(f["reverse"][r].value)
            if number != row.number or " ".join(prompt.split()) != row.prompt or reverse != row.reverse_proposed:
                out = set_row(out, r, prompt=prompt, number=number, reverse_proposed=reverse)
            for c, cell in enumerate(row.cells):
                text = f["cells"][r][c].value or ""
                if " ".join(text.split()) != cell.text:
                    out = set_cell(out, r, c, text)
        return out

    def _run(self, operation, message):
        matrix = self.current()
        if matrix is None:
            return
        try:
            updated = operation(self._collect(matrix))
        except (ValueError, IndexError) as error:
            self.status.value = f"Matrix change rejected: {error}"
            self.owner._update()
            return
        if updated is not matrix:
            self.store(updated, message)
        self.owner.relayout()
        self.owner._update()

    def _apply(self, event=None):
        self._run(lambda m: m, "Matrix edited; verification and approvals reset.")

    def _add_row(self, event=None):
        self._run(lambda m: add_row(m, None, ""), "Matrix row added; verification reset.")

    def _add_column(self, event=None):
        self._run(lambda m: add_column(m, None, ""), "Matrix column added; verification reset.")

    def _accept_flagged(self, event=None):
        def accept_all(m):
            for r, c in m.unresolved_cells:
                m = accept_cell(m, r, c)
            return m
        self._run(accept_all, "Flagged cells accepted as shown; verification reset.")

    def _row_op(self, index, kind):
        def handler(event=None):
            op = {"up": lambda m: move_row(m, index, -1), "down": lambda m: move_row(m, index, 1),
                  "delete": lambda m: delete_row(m, index)}[kind]
            self._run(op, "Matrix rows changed; verification reset.")
        return handler

    def _column_op(self, index, kind):
        def handler(event=None):
            op = {"left": lambda m: move_column(m, index, -1), "right": lambda m: move_column(m, index, 1),
                  "delete": lambda m: delete_column(m, index)}[kind]
            self._run(op, "Matrix columns changed; verification reset.")
        return handler

    def _verify(self, event=None):
        matrix = self.current()
        if matrix is None:
            return
        try:
            collected = self._collect(matrix)
            verified = verify_matrix(collected)
        except (ValueError, IndexError) as error:
            self.status.value = str(error)
            self.owner._update()
            return
        review = self.owner.get_review()
        found = list(self.matrices())
        found[self.owner.matrix_index] = verified
        self.owner.set_review(replace(review, matrices=tuple(found)))
        self.owner.relayout()
        self.status.value = (
            "VERIFIED grid mapping. Numeric codes and reverse keys are still NOT "
            "applied unless you tick the confirmations below."
        )
        self.owner._update()

    def _commit(self, event=None):
        matrix = self.current()
        if matrix is None:
            return
        if self._collect(matrix) is not matrix:
            self.status.value = "Apply and verify your grid edits before using the matrix."
            self.owner._update()
            return
        try:
            questions = matrix_to_questions(
                matrix, accept_codes=bool(self.codes_confirm.value),
                accept_reverse=bool(self.reverse_confirm.value),
            )
        except ValueError as error:
            self.status.value = f"Cannot use matrix: {error}"
            self.owner._update()
            return
        if self.owner.on_matrix_commit(questions, matrix.title):
            self.status.value = (
                f"{len(questions)} matrix rows copied into the editable draft "
                + ("with confirmed numeric codes." if self.codes_confirm.value
                   else "as labelled choices (no numeric scoring).")
            )
        self.owner._update()

    async def _on_pick(self, event=None):
        try:
            self.owner.matrix_index = int(self.picker.value)
        except (TypeError, ValueError):
            return
        matrix = self.current()
        self.codes_confirm.value = False
        self.reverse_confirm.value = False
        if matrix is not None and matrix.rows and matrix.source_kind != "docx_table":
            await self.owner.go_to_page(matrix.rows[0].page)
        self.owner.relayout()
        self.owner._update()


__all__ = [
    "SpatialReviewController", "MatrixEditor", "png_size",
    "OCR_HIGH_THRESHOLD", "OCR_REVIEW_THRESHOLD",
]
