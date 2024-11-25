import logging
from PyQt6.QtWidgets import QPushButton, QWidget, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QCursor
from core.widgets.base import BaseWidget
from core.validation.widgets.yasb.windows_desktops import VALIDATION_SCHEMA
from core.event_service import EventService
from pyvda import VirtualDesktop, get_virtual_desktops

class WorkspaceButton(QPushButton):
    def __init__(self, workspace_index: int, label: str = None, active_label: str = None, parent=None):
        super().__init__(parent)
        
        self.workspace_index = workspace_index
        self.setProperty("class", "ws-btn")
        self.default_label = label if label else str(workspace_index)
        self.active_label = active_label if active_label else self.default_label
        self.setText(self.default_label)
        self.clicked.connect(self.activate_workspace)
        self.parent_widget = parent
        self.workspace_animation = self.parent_widget._switch_workspace_animation
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
       
    def activate_workspace(self):
        try:
            VirtualDesktop(self.workspace_index).go(self.workspace_animation)
            if isinstance(self.parent_widget, WorkspaceWidget):
                # Emit event to update desktops on all monitors
                self.parent_widget._event_service.emit_event(
                    "virtual_desktop_changed",
                    {"index": self.workspace_index}
                )
        except Exception:
            logging.exception(f"Failed to focus desktop at index {self.workspace_index}")


class WorkspaceWidget(BaseWidget):
    d_signal_virtual_desktop_changed = pyqtSignal(dict)
    d_signal_virtual_desktop_update  = pyqtSignal(dict)
    validation_schema = VALIDATION_SCHEMA
    def __init__(
            self,
            label_workspace_btn: str,
            label_workspace_active_btn: str,
            switch_workspace_animation: bool,
            container_padding: dict,
    ):
        super().__init__(class_name="windows-desktops")
        self._event_service = EventService()
        
        self.d_signal_virtual_desktop_changed.connect(self._on_desktop_changed)
        self._event_service.register_event("virtual_desktop_changed", self.d_signal_virtual_desktop_changed)
        
        self.d_signal_virtual_desktop_update.connect(self._on_update_desktops)
        self._event_service.register_event("virtual_desktop_update", self.d_signal_virtual_desktop_update)
        
        self._label_workspace_btn = label_workspace_btn
        self._label_workspace_active_btn = label_workspace_active_btn
        self._padding = container_padding
        self._switch_workspace_animation = switch_workspace_animation
        self._virtual_desktops = range(1, len(get_virtual_desktops()) + 1)
        self._prev_workspace_index = None
        self._curr_workspace_index = VirtualDesktop.current().number
        self._workspace_buttons: list[WorkspaceButton] = []

        # Disable default mouse event handling inherited from BaseWidget
        self.mousePressEvent = None

        # Construct container which holds workspace buttons
        self._workspace_container_layout: QHBoxLayout = QHBoxLayout()
        self._workspace_container_layout.setSpacing(0)
        self._workspace_container_layout.setContentsMargins(self._padding['left'],self._padding['top'],self._padding['right'],self._padding['bottom'])
        self._workspace_container: QWidget = QWidget()
        self._workspace_container.setLayout(self._workspace_container_layout)
        self._workspace_container.setProperty("class", "widget-container")
        self.widget_layout.addWidget(self._workspace_container)

        self.timer_interval = 2000
        self.callback_timer = "update_desktops"
        self.register_callback(self.callback_timer, self.on_update_desktops)
        self.start_timer()
    
    def _on_desktop_changed(self, event_data: dict):
        self._curr_workspace_index = event_data["index"]
        for button in self._workspace_buttons:
            self._update_button(button)
            
    def on_update_desktops(self):
        # Emit event to update desktops on all monitors
        self._event_service.emit_event(
            "virtual_desktop_update",
            {"index": VirtualDesktop.current().number}
        )
        
    def _on_update_desktops(self):        
        self._virtual_desktops_check = list(range(1, len(get_virtual_desktops()) + 1))
        self._curr_workspace_index_check = VirtualDesktop.current().number
        if self._virtual_desktops != self._virtual_desktops_check or self._curr_workspace_index != self._curr_workspace_index_check:
            self._virtual_desktops = self._virtual_desktops_check
            self._curr_workspace_index = self._curr_workspace_index_check
            self._add_or_remove_buttons()
            
    def _clear_container_layout(self):
        for i in reversed(range(self._workspace_container_layout.count())):
            old_workspace_widget = self._workspace_container_layout.itemAt(i).widget()
            self._workspace_container_layout.removeWidget(old_workspace_widget)
            old_workspace_widget.setParent(None)

    def _update_button(self, workspace_btn: WorkspaceButton) -> None:  
        if workspace_btn.workspace_index == self._curr_workspace_index:
            workspace_btn.setProperty("class", "ws-btn-active")
            workspace_btn.setStyleSheet('')
            workspace_btn.setText(workspace_btn.active_label)
        else:
            workspace_btn.setProperty("class", "ws-btn")
            workspace_btn.setStyleSheet('')
            workspace_btn.setText(workspace_btn.default_label)
 
    def _add_or_remove_buttons(self) -> None:
        changes_made = False
        current_indices = set(self._virtual_desktops)
        existing_indices = set(btn.workspace_index for btn in self._workspace_buttons)
        # Handle removals
        indices_to_remove = existing_indices - current_indices
        if indices_to_remove:
            self._workspace_buttons = [
                btn for btn in self._workspace_buttons 
                if btn.workspace_index not in indices_to_remove
            ]
            changes_made = True

        # Handle additions
        for desktop_index in current_indices:
            # Find existing button with matching workspace_index
            existing_button = next(
                (btn for btn in self._workspace_buttons if btn.workspace_index == desktop_index),
                None
            )
            if existing_button:
                self._update_button(existing_button)
            else:
                new_button = self._try_add_workspace_button(desktop_index)
                self._update_button(new_button)
                changes_made = True
        # Rebuild layout only if changes occurred
        if changes_made:
            self._workspace_buttons.sort(key=lambda btn: btn.workspace_index)
            self._clear_container_layout()
            
            for workspace_btn in self._workspace_buttons:
                self._workspace_container_layout.addWidget(workspace_btn)

    def _get_workspace_label(self, workspace_index):
        label = self._label_workspace_btn.format(
            index=workspace_index
        )
        active_label = self._label_workspace_active_btn.format(
            index=workspace_index
        )
        return label, active_label

    def _try_add_workspace_button(self, workspace_index: int) -> WorkspaceButton:
        workspace_button_indexes = [ws_btn.workspace_index for ws_btn in self._workspace_buttons]
        if workspace_index not in workspace_button_indexes:
            ws_label, ws_active_label = self._get_workspace_label(workspace_index)
            workspace_btn = WorkspaceButton(workspace_index, ws_label, ws_active_label, self)
            self._update_button(workspace_btn)
            self._workspace_buttons.append(workspace_btn)
            return workspace_btn