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

import carb
import omni.ext
import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, UsdGeom

from .ui_builder import UIBuilder


class Extension(omni.ext.IExt):
    """The Extension class"""

    def on_startup(self, ext_id):
        """Method called when the extension is loaded/enabled"""
        carb.log_info(f"on_startup {ext_id}")
        ext_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)

        # Build the extension window immediately and wire the setup button to scene creation.
        self.ui_builder = UIBuilder(
            window_title="Ncume CPS Build Environment",
            menu_path="Window/Ncume Cps Build Environment",
            on_setup_scene=self.setup_scene,
        )
        self.ui_builder.show_window()

    def on_shutdown(self):
        """Method called when the extension is disabled"""
        carb.log_info(f"on_shutdown")

        # clean up UI
        self.ui_builder.cleanup()

    def setup_scene(self):
        """Create a ground plane and a 5 m by 6 m walled rectangle."""
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            carb.log_error("No open USD stage to set up the scene.")
            return

        # Keep the stage in meters with Z as the vertical axis so dimensions below map
        # directly to the requested real-world sizes.
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)

        world_path = Sdf.Path("/World")
        if not stage.GetPrimAtPath(world_path):
            UsdGeom.Xform.Define(stage, world_path)

        scene_root = Sdf.Path("/World/BuildEnvironment")
        if not stage.GetPrimAtPath(scene_root):
            UsdGeom.Xform.Define(stage, scene_root)

        # Create a large, flat floor under the test area so the room has a visible base.
        self._create_ground(stage, scene_root.AppendChild("GroundPlane"), size_xy=(20.0, 20.0), thickness=0.05)

        # Room interior requested by the user: 5 m x 6 m, enclosed by 0.1 m walls.
        interior_width = 5.0
        interior_depth = 6.0
        wall_thickness = 0.1
        wall_height = 0.5
        wall_color = Gf.Vec3f(0.2, 0.2, 0.2)

        # The north/south walls span the full width plus the side-wall thickness so the
        # four wall segments meet cleanly at the corners.
        self._create_box(
            stage,
            scene_root.AppendChild("NorthWall"),
            size=(interior_width + 2 * wall_thickness, wall_thickness, wall_height),
            translate=(0.0, interior_depth / 2 + wall_thickness / 2, wall_height / 2),
            color=wall_color,
        )
        self._create_box(
            stage,
            scene_root.AppendChild("SouthWall"),
            size=(interior_width + 2 * wall_thickness, wall_thickness, wall_height),
            translate=(0.0, -(interior_depth / 2 + wall_thickness / 2), wall_height / 2),
            color=wall_color,
        )
        # The east/west walls keep the interior depth exactly 6 m and sit centered on Y.
        self._create_box(
            stage,
            scene_root.AppendChild("EastWall"),
            size=(wall_thickness, interior_depth, wall_height),
            translate=(interior_width / 2 + wall_thickness / 2, 0.0, wall_height / 2),
            color=wall_color,
        )
        self._create_box(
            stage,
            scene_root.AppendChild("WestWall"),
            size=(wall_thickness, interior_depth, wall_height),
            translate=(-(interior_width / 2 + wall_thickness / 2), 0.0, wall_height / 2),
            color=wall_color,
        )

        carb.log_info("Created ground plane and 5 m x 6 m walled test area at /World/BuildEnvironment.")

    def _create_ground(self, stage, prim_path, size_xy, thickness):
        """Create a flat box that serves as the ground surface."""
        self._create_box(
            stage,
            prim_path,
            size=(size_xy[0], size_xy[1], thickness),
            translate=(0.0, 0.0, -thickness / 2),
        )

    def _create_box(self, stage, prim_path, size, translate, color=None):
        """Create or update a box mesh from a scaled USD cube prim."""
        cube = UsdGeom.Cube.Define(stage, prim_path)
        cube.CreateSizeAttr(1.0)
        # Display color lets us tint the generated prim without introducing a separate material.
        if color is not None:
            cube.CreateDisplayColorAttr().Set([color])

        prim = cube.GetPrim()
        xformable = UsdGeom.Xformable(prim)
        # Rebuild the authored transform ops each time so rerunning setup_scene updates
        # existing prims deterministically instead of stacking transforms.
        xformable.ClearXformOpOrder()

        translate_op = xformable.AddTranslateOp()
        translate_op.Set(Gf.Vec3d(*translate))

        scale_op = xformable.AddScaleOp()
        scale_op.Set(Gf.Vec3f(*size))
