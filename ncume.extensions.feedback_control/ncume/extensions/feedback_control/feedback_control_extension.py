import os

import omni.ext
import omni.ui as ui
from isaacsim.core.api import World

# these namespaces are related to the import paths
from isaacsim.examples.browser import get_instance as get_browser_instance
from isaacsim.examples.interactive.base_sample import BaseSampleUITemplate
from ncume.extensions.feedback_control import feedback_control


class feedback_control_extension(omni.ext.IExt):
    def on_startup(self, ext_id):
        # Create a window when the Extension starts
        self._window = ui.Window("My Interactive Tool", width=300, height=200)
        with self._window.frame:
            with ui.VStack():
                ui.Label("Click the button to run my custom code")
                
                # Button interaction
                ui.Button("Run My Code", clicked_fn=self._on_button_click)
                ui.Button("Reset Scene", clicked_fn=self._reset_world)

    def _on_button_click(self):
        # Put your own logic here
        print("Running custom code...")
        
        # Example: add a cube into the scene
        from isaacsim.core.api.objects import DynamicCuboid
        import numpy as np
        
        DynamicCuboid(
            prim_path="/World/MyCube",
            name="my_cube",
            position=np.array([0, 0, 1.0]),
            scale=np.array([0.5, 0.5, 0.5]),
            color=np.array([0.2, 0.3, 0.9])
        )

    def _reset_world(self):
        # Interact with Isaac Sim Core API
        world = World.instance()
        if world:
            world.reset()

    def on_shutdown(self):
        # Clean up the UI when the Extension closes
        self._window = None
        
print("Extension [feedback_control] startup")