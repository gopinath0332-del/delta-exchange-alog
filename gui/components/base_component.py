"""Base component classes for reusable GUI components."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

import dearpygui.dearpygui as dpg

from core.logger import get_logger

logger = get_logger(__name__)


class BaseComponent(ABC):
    """Abstract base class for all GUI components."""

    def __init__(self, tag: Optional[str] = None):
        """
        Initialize base component.

        Args:
            tag: Optional unique tag for the component
        """
        self.tag = tag or dpg.generate_uuid()
        self.visible = True
        self.enabled = True
        logger.debug("Component initialized", component=self.__class__.__name__, tag=self.tag)

    @abstractmethod
    def render(self, parent: Optional[str] = None) -> str:
        """
        Render the component.

        Args:
            parent: Parent container tag

        Returns:
            Component tag
        """
        pass

    def show(self):
        """Show the component."""
        if dpg.does_item_exist(self.tag):
            dpg.show_item(self.tag)
            self.visible = True
            logger.debug("Component shown", tag=self.tag)

    def hide(self):
        """Hide the component."""
        if dpg.does_item_exist(self.tag):
            dpg.hide_item(self.tag)
            self.visible = False
            logger.debug("Component hidden", tag=self.tag)

    def enable(self):
        """Enable the component."""
        if dpg.does_item_exist(self.tag):
            dpg.enable_item(self.tag)
            self.enabled = True

    def disable(self):
        """Disable the component."""
        if dpg.does_item_exist(self.tag):
            dpg.disable_item(self.tag)
            self.enabled = False

    def cleanup(self):
        """Clean up component resources."""
        if dpg.does_item_exist(self.tag):
            dpg.delete_item(self.tag)
            logger.debug("Component cleaned up", tag=self.tag)

    @abstractmethod
    def update(self, data: Any):
        """
        Update component with new data.

        Args:
            data: New data to display
        """
        pass


class BasePanel(BaseComponent):
    """Base class for panel components."""

    def __init__(
        self,
        title: str,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = -1,
        collapsible: bool = True,
        border: bool = True,
    ):
        """
        Initialize panel.

        Args:
            title: Panel title
            tag: Optional unique tag
            width: Panel width (-1 for auto)
            height: Panel height (-1 for auto)
            collapsible: Whether panel can be collapsed
            border: Whether to show border
        """
        super().__init__(tag)
        self.title = title
        self.width = width
        self.height = height
        self.collapsible = collapsible
        self.border = border

    def render(self, parent: Optional[str] = None) -> str:
        """Render the panel."""
        with dpg.child_window(
            tag=self.tag,
            parent=parent,
            width=self.width,
            height=self.height,
            border=self.border,
        ):
            if self.title:
                dpg.add_text(self.title, color=(200, 200, 200))
                dpg.add_separator()

            self.render_content()

        return self.tag

    @abstractmethod
    def render_content(self):
        """Render panel content. Override in subclasses."""
        pass

    def update(self, data: Any):
        """Update panel content."""
        pass


class BaseTable(BaseComponent):
    """Base class for table components."""

    def __init__(
        self,
        tag: Optional[str] = None,
        columns: Optional[List[str]] = None,
        sortable: bool = True,
        resizable: bool = True,
        reorderable: bool = False,
        hideable: bool = False,
        row_background: bool = True,
        borders_inner_h: bool = True,
        borders_outer_h: bool = True,
        borders_inner_v: bool = True,
        borders_outer_v: bool = True,
    ):
        """
        Initialize table.

        Args:
            tag: Optional unique tag
            columns: List of column names
            sortable: Enable column sorting
            resizable: Enable column resizing
            reorderable: Enable column reordering
            hideable: Enable column hiding
            row_background: Alternate row background
            borders_inner_h: Show inner horizontal borders
            borders_outer_h: Show outer horizontal borders
            borders_inner_v: Show inner vertical borders
            borders_outer_v: Show outer vertical borders
        """
        super().__init__(tag)
        self.columns = columns or []
        self.sortable = sortable
        self.resizable = resizable
        self.reorderable = reorderable
        self.hideable = hideable
        self.row_background = row_background
        self.borders_inner_h = borders_inner_h
        self.borders_outer_h = borders_outer_h
        self.borders_inner_v = borders_inner_v
        self.borders_outer_v = borders_outer_v
        self.rows_data: List[Dict[str, Any]] = []

    def render(self, parent: Optional[str] = None) -> str:
        """Render the table."""
        with dpg.table(
            tag=self.tag,
            parent=parent,
            header_row=True,
            resizable=self.resizable,
            reorderable=self.reorderable,
            hideable=self.hideable,
            sortable=self.sortable,
            row_background=self.row_background,
            borders_innerH=self.borders_inner_h,
            borders_outerH=self.borders_outer_h,
            borders_innerV=self.borders_inner_v,
            borders_outerV=self.borders_outer_v,
        ):
            # Add columns
            for col in self.columns:
                dpg.add_table_column(label=col)

        return self.tag

    def update(self, data: List[Dict[str, Any]]):
        """
        Update table with new data.

        Args:
            data: List of row dictionaries
        """
        if not dpg.does_item_exist(self.tag):
            return

        self.rows_data = data

        # Clear existing rows
        children = dpg.get_item_children(self.tag, slot=1)  # slot 1 is rows
        if children:
            for child in children:
                dpg.delete_item(child)

        # Add new rows
        for row_data in data:
            with dpg.table_row(parent=self.tag):
                for col in self.columns:
                    value = row_data.get(col, "")
                    self.render_cell(col, value, row_data)

    def render_cell(self, column: str, value: Any, row_data: Dict[str, Any]):
        """
        Render a table cell. Override for custom rendering.

        Args:
            column: Column name
            value: Cell value
            row_data: Full row data
        """
        dpg.add_text(str(value))

    def add_row(self, row_data: Dict[str, Any]):
        """
        Add a single row to the table.

        Args:
            row_data: Row data dictionary
        """
        self.rows_data.append(row_data)
        with dpg.table_row(parent=self.tag):
            for col in self.columns:
                value = row_data.get(col, "")
                self.render_cell(col, value, row_data)

    def clear(self):
        """Clear all table rows."""
        self.rows_data = []
        children = dpg.get_item_children(self.tag, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)


class BaseWindow(BaseComponent):
    """Base class for window components."""

    def __init__(
        self,
        title: str,
        tag: Optional[str] = None,
        width: int = 800,
        height: int = 600,
        pos: Optional[tuple] = None,
        modal: bool = False,
        no_close: bool = False,
        no_resize: bool = False,
        no_move: bool = False,
        on_close: Optional[Callable] = None,
    ):
        """
        Initialize window.

        Args:
            title: Window title
            tag: Optional unique tag
            width: Window width
            height: Window height
            pos: Window position (x, y)
            modal: Whether window is modal
            no_close: Disable close button
            no_resize: Disable resizing
            no_move: Disable moving
            on_close: Callback when window closes
        """
        super().__init__(tag)
        self.title = title
        self.width = width
        self.height = height
        self.pos = pos
        self.modal = modal
        self.no_close = no_close
        self.no_resize = no_resize
        self.no_move = no_move
        self.on_close = on_close

    def render(self, parent: Optional[str] = None) -> str:
        """Render the window."""
        with dpg.window(
            tag=self.tag,
            label=self.title,
            width=self.width,
            height=self.height,
            pos=self.pos,
            modal=self.modal,
            no_close=self.no_close,
            no_resize=self.no_resize,
            no_move=self.no_move,
            on_close=self._handle_close,
        ):
            self.render_content()

        return self.tag

    def _handle_close(self):
        """Handle window close event."""
        if self.on_close:
            self.on_close()
        self.cleanup()

    @abstractmethod
    def render_content(self):
        """Render window content. Override in subclasses."""
        pass

    def update(self, data: Any):
        """Update window content."""
        pass
