"""Molecules view — molecule library with table and SAR analysis."""

from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ...utils.logger import get_logger
from ..components import search_bar, two_panel
from ..utils import (
    get_status_color,
    run_in_background,
    safe_set_value,
    t,
)
from .base import BaseView

logger = get_logger(__name__)


class MoleculesView(BaseView):
    """Molecule library view."""

    view_name = "molecules"

    def __init__(self, app):
        super().__init__(app)
        self._molecules: list[dict] = []
        self._total = 0
        self._page = 1
        self._page_size = 50
        self._selected_mol_id: str | None = None

    def _build(self) -> None:
        two_panel(
            left_tag="mol_left_panel",
            right_tag="mol_right_panel",
            left_width=-1,
            left_builder=self._build_left,
            right_builder=self._build_right,
        )

    def _build_left(self) -> None:
        self._build_toolbar()
        dpg.add_spacer(height=8)
        self._build_table()

    def _build_right(self) -> None:
        self._build_analysis_panel()

    def _build_toolbar(self) -> None:
        with dpg.group(horizontal=True):
            search_bar(
                input_tag="mol_search_input",
                callback=self._on_search,
                placeholder=t("molecules.search"),
                input_width=300,
            )
            dpg.add_spacer(width=8)
            add_btn = dpg.add_button(
                label=t("molecules.add"),
                width=100,
                height=32,
                callback=self._on_add,
            )
            dpg.bind_item_theme(add_btn, "success_button")

        dpg.add_spacer(height=4)
        dpg.add_text(
            t("molecules.total", count=0),
            tag="mol_total_text",
            color=(140, 140, 150),
        )

    def _build_table(self) -> None:
        with dpg.table(
            tag="mol_table",
            header_row=True,
            resizable=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            height=500,
            scrollY=True,
            freeze_rows=1,
        ):
            dpg.add_table_column(label=t("molecules.smiles"), width_stretch=True)
            dpg.add_table_column(label=t("molecules.name"), width_stretch=True)
            dpg.add_table_column(label=t("molecules.activity"), width_stretch=True)
            dpg.add_table_column(label=t("molecules.source"), width_stretch=True)
            dpg.add_table_column(label=t("molecules.status"), width_stretch=True)

        with dpg.group(horizontal=True, tag="mol_pagination"):
            dpg.add_button(label="<", width=32, height=28, callback=self._prev_page)
            dpg.add_text("1", tag="mol_page_num")
            dpg.add_button(label=">", width=32, height=28, callback=self._next_page)

    def _build_analysis_panel(self) -> None:
        with dpg.group(tag="mol_analysis"):
            dpg.add_text(t("molecules.analysis"), color=(180, 180, 190))
            dpg.add_spacer(height=8)

            with dpg.group(horizontal=True):
                for tab_name in ["Overview", "Cliffs", "Correction", "R-Group", "Relations", "Analytics"]:
                    dpg.add_button(
                        label=tab_name,
                        width=80,
                        height=28,
                        callback=self._on_analysis_tab,
                        user_data=tab_name.lower(),
                    )

            dpg.add_spacer(height=8)
            dpg.add_child_window(
                tag="mol_analysis_content",
                autosize_x=True,
                height=450,
                border=True,
            )

    def _on_analysis_tab(self, sender: int, app_data: Any, user_data: str) -> None:
        pass

    def refresh(self) -> None:
        if not self.state.library_root:
            return
        self._load_molecules()

    def _load_molecules(self) -> None:
        def _worker():
            try:
                resp = self.api.list_molecules(
                    self.state.library_root,
                    page=self._page,
                    page_size=self._page_size,
                )
                self._molecules = [self._mol_to_dict(m) for m in resp.items]
                self._total = resp.total
                self._render_table()
                self._update_pagination()
            except Exception as e:
                logger.error("Failed to load molecules: %s", e)

        run_in_background(_worker)

    def _mol_to_dict(self, mol) -> dict:
        return {
            "mol_id": mol.mol_id,
            "smiles": mol.smiles,
            "name": mol.name,
            "activity": mol.activity,
            "source_type": mol.source_type,
            "status": mol.status,
        }

    def _render_table(self) -> None:
        table = "mol_table"
        children = dpg.get_item_children(table, 1) or []
        for child in children:
            if dpg.does_item_exist(child) and dpg.get_item_info(child).get("type") == "mvAppItemType::mvTableRow":
                dpg.delete_item(child)

        for mol in self._molecules:
            with dpg.table_row(parent=table):
                dpg.add_text(mol.get("smiles", "")[:30])
                dpg.add_text(mol.get("name", ""))
                activity = mol.get("activity")
                dpg.add_text(f"{activity:.2f}" if activity is not None else "-")
                dpg.add_text(mol.get("source_type", ""))
                status = mol.get("status", "")
                dpg.add_text(status, color=get_status_color(status))

    def _update_pagination(self) -> None:
        safe_set_value("mol_total_text", t("molecules.total", count=self._total))
        safe_set_value("mol_page_num", str(self._page))

    def _on_search(self, sender: int, app_data: Any, user_data: Any) -> None:
        query = dpg.get_value("mol_search_input")
        if not query or not self.state.library_root:
            return

        def _worker():
            try:
                results = self.api.search_molecules(self.state.library_root, query)
                self._molecules = [self._mol_to_dict(m) for m in results]
                self._total = len(results)
                self._render_table()
                self._update_pagination()
            except Exception as e:
                logger.error("Failed to search molecules: %s", e)

        run_in_background(_worker)

    def _on_add(self, sender: int, app_data: Any, user_data: Any) -> None:
        pass

    def _prev_page(self, sender: int, app_data: Any, user_data: Any) -> None:
        if self._page > 1:
            self._page -= 1
            self.refresh()

    def _next_page(self, sender: int, app_data: Any, user_data: Any) -> None:
        if self._page * self._page_size < self._total:
            self._page += 1
            self.refresh()
