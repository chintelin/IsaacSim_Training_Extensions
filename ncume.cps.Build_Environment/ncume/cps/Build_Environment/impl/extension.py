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
import random
from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics

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
            on_generate_objects=self.generate_objects,
            on_clear_objects=self.clear_objects,
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

        scene_root = Sdf.Path("/World/BuildEnvironment")
        if stage.GetPrimAtPath(scene_root):
            carb.log_warn("Scene setup skipped because /World/BuildEnvironment already exists.")
            return

        # Keep the stage in meters with Z as the vertical axis so dimensions below map
        # directly to the requested real-world sizes.
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)

        scene_root = self._ensure_scene_root(stage)
        self._ensure_physics_scene(stage)

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
            enable_collision=True,
            collision_approximation="boundingCube",
            rigid_body=True,
            kinematic=True,
        )
        self._create_box(
            stage,
            scene_root.AppendChild("SouthWall"),
            size=(interior_width + 2 * wall_thickness, wall_thickness, wall_height),
            translate=(0.0, -(interior_depth / 2 + wall_thickness / 2), wall_height / 2),
            color=wall_color,
            enable_collision=True,
            collision_approximation="boundingCube",
            rigid_body=True,
            kinematic=True,
        )
        # The east/west walls keep the interior depth exactly 6 m and sit centered on Y.
        self._create_box(
            stage,
            scene_root.AppendChild("EastWall"),
            size=(wall_thickness, interior_depth, wall_height),
            translate=(interior_width / 2 + wall_thickness / 2, 0.0, wall_height / 2),
            color=wall_color,
            enable_collision=True,
            collision_approximation="boundingCube",
            rigid_body=True,
            kinematic=True,
        )
        self._create_box(
            stage,
            scene_root.AppendChild("WestWall"),
            size=(wall_thickness, interior_depth, wall_height),
            translate=(-(interior_width / 2 + wall_thickness / 2), 0.0, wall_height / 2),
            color=wall_color,
            enable_collision=True,
            collision_approximation="boundingCube",
            rigid_body=True,
            kinematic=True,
        )

        carb.log_info("Created ground plane and 5 m x 6 m walled test area at /World/BuildEnvironment.")

    def generate_objects(self):
        """Generate one random cube above the room so it can fall under simulation."""
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            carb.log_error("No open USD stage to generate objects on.")
            return

        # Reuse the same room dimensions so cubes stay inside the enclosure.
        scene_root = self._ensure_scene_root(stage)
        self._ensure_physics_scene(stage)
        objects_root = scene_root.AppendChild("GeneratedObjects")
        if not stage.GetPrimAtPath(objects_root):
            UsdGeom.Xform.Define(stage, objects_root)

        interior_width = 5.0
        interior_depth = 6.0
        cube_size = random.uniform(0.3, 0.6)
        x_pos = random.uniform(-(interior_width / 2) + cube_size / 2, (interior_width / 2) - cube_size / 2)
        y_pos = random.uniform(-(interior_depth / 2) + cube_size / 2, (interior_depth / 2) - cube_size / 2)
        z_pos = random.uniform(1.0, 5.0)
        rotation = (
            random.uniform(0.0, 360.0),
            random.uniform(0.0, 360.0),
            random.uniform(0.0, 360.0),
        )
        cube_index = len(stage.GetPrimAtPath(objects_root).GetChildren())

        # Spawn a single dynamic cube per click so simulation can drop it onto the
        # collider-backed ground and walls.
        cube_path = objects_root.AppendChild(f"Cube_{cube_index:02d}")
        self._create_box(
            stage,
            cube_path,
            size=(cube_size, cube_size, cube_size),
            translate=(x_pos, y_pos, z_pos),
            rotation=rotation,
            enable_collision=True,
            rigid_body=True,
        )

        carb.log_info(f"Generated falling cube at {cube_path}.")

    def clear_objects(self):
        """Remove all generated cubes while keeping the room geometry intact."""
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            carb.log_error("No open USD stage to clear objects from.")
            return

        objects_root = Sdf.Path("/World/BuildEnvironment/GeneratedObjects")
        if stage.GetPrimAtPath(objects_root):
            stage.RemovePrim(objects_root)
            carb.log_info("Removed all generated cubes from /World/BuildEnvironment/GeneratedObjects.")
            return

        carb.log_info("No generated cubes found to remove.")

    def _ensure_scene_root(self, stage):
        """Ensure the extension scene root exists and return its path."""
        world_path = Sdf.Path("/World")
        if not stage.GetPrimAtPath(world_path):
            UsdGeom.Xform.Define(stage, world_path)

        scene_root = Sdf.Path("/World/BuildEnvironment")
        if not stage.GetPrimAtPath(scene_root):
            UsdGeom.Xform.Define(stage, scene_root)

        return scene_root

    def _ensure_physics_scene(self, stage):
        """Ensure there is a physics scene so dynamic objects respond to gravity."""
        physics_scene_path = Sdf.Path("/World/PhysicsScene")
        if stage.GetPrimAtPath(physics_scene_path):
            return physics_scene_path

        physics_scene = UsdPhysics.Scene.Define(stage, physics_scene_path)
        physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        physics_scene.CreateGravityMagnitudeAttr().Set(9.81)
        return physics_scene_path

    def _create_ground(self, stage, prim_path, size_xy, thickness):
        """Create a flat box that serves as the ground surface."""
        self._create_box(
            stage,
            prim_path,
            size=(size_xy[0], size_xy[1], thickness),
            translate=(0.0, 0.0, -thickness / 2),
            enable_collision=True,
            collision_approximation="boundingCube",
            rigid_body=True,
            kinematic=True,
        )

    def _create_box(
        self,
        stage,
        prim_path,
        size,
        translate,
        color=None,
        rotation=None,
        enable_collision=False,
        collision_approximation=None,
        rigid_body=False,
        kinematic=False,
    ):
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

        if rotation is not None:
            rotate_op = xformable.AddRotateXYZOp()
            rotate_op.Set(Gf.Vec3f(*rotation))

        scale_op = xformable.AddScaleOp()
        scale_op.Set(Gf.Vec3f(*size))

        if enable_collision:
            UsdPhysics.CollisionAPI.Apply(prim)
            if collision_approximation is not None:
                mesh_collision_api = UsdPhysics.MeshCollisionAPI.Apply(prim)
                mesh_collision_api.CreateApproximationAttr().Set(collision_approximation)

        if rigid_body:
            rigid_body_api = UsdPhysics.RigidBodyAPI.Apply(prim)
            rigid_body_api.CreateRigidBodyEnabledAttr(True)
            rigid_body_api.CreateKinematicEnabledAttr(kinematic)
            # Enable CCD only for dynamic rigid bodies. PhysX ignores CCD on
            # kinematic bodies and emits a warning if both are authored.
            if not kinematic:
                physx_rigid_body_api = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
                physx_rigid_body_api.CreateEnableCCDAttr(True)
