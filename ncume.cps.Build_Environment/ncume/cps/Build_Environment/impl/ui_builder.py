# MIT License
# 
# Copyright (c) 2024 <COPYRIGHT_HOLDERS>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# 

import omni.kit.ui
import omni.ui as ui


class UIBuilder:
    """Manage extension UI"""

    def __init__(
        self,
        window_title,
        menu_path=None,
        on_setup_scene=None,
        on_generate_objects=None,
        on_clear_objects=None,
    ):
        self._menu = None
        self._window = None

        self._menu_path = menu_path
        self._on_clear_objects = on_clear_objects
        self._on_generate_objects = on_generate_objects
        self._on_setup_scene = on_setup_scene
        self._window_title = window_title
        
        # create menu
        if self._menu_path:
            self._menu = omni.kit.ui.get_editor_menu().add_item(self._menu_path, self.on_toggle, toggle=True, value=False)

    def on_toggle(self, *args, **kwargs):
        """Toggle window visibility"""
        self.build_ui()
        if self._window is not None:
            self._window.visible = not self._window.visible

    def show_window(self):
        """Build and show the extension window."""
        self.build_ui()
        if self._window is not None:
            self._window.visible = True

    def build_ui(self):
        """Build the Graphical User Interface (GUI) in the underlying windowing system"""
        if not self._window:
            self._window = ui.Window(title=self._window_title, visible=False, width=300, height=300)
            with self._window.frame:
                with ui.VStack(spacing=4):
                    ui.Button(
                        "Setup the testing Scene",
                        clicked_fn=self._on_setup_scene or (lambda: None),
                    )
                    ui.Button(
                        "Generate Objects",
                        clicked_fn=self._on_generate_objects or (lambda: None),
                    )
                    ui.Button(
                        "Erase All Cubes",
                        clicked_fn=self._on_clear_objects or (lambda: None),
                    )

    def cleanup(self):
        """Clean up window and menu"""
        # destroy window
        if self._window is not None:
            self._window.destroy()
            self._window = None
        # destroy menu
        if self._menu is not None:
            try:
                omni.kit.ui.get_editor_menu().remove_item(self._menu)
            except:
                omni.kit.ui.get_editor_menu().remove_item(self._menu_path)
            self._menu = None
