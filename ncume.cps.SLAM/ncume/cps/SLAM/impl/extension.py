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
from isaacsim.storage.native import get_assets_root_path
import omni.ext
import omni.kit.app
import omni.kit.undo
import omni.usd
from omni.isaac.core.utils.stage import add_reference_to_stage
import random
from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics

from .ui_builder import UIBuilder


class Extension(omni.ext.IExt):
    """The Extension class"""

    # ROS 2 update: keep the mounted RealSense and its OmniGraph publisher paths centralized.
    _REALSENSE_SENSOR_PATH = "/World/Jetbot/chassis/RealSense_D455"
    _ROS2_GRAPH_PATH = "/World/Jetbot/ROS2RealSenseGraph"

    def on_startup(self, ext_id):
        """Method called when the extension is loaded/enabled"""
        carb.log_info(f"on_startup {ext_id}")
        ext_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        self._ros2_context = None
        self._ros2_node = None
        self._start_ros2_node()

        # Build the extension window immediately and wire the setup button to scene creation.
        self.ui_builder = UIBuilder(
            window_title="Ncume CPS Build Environment",
            menu_path="Window/Ncume Cps Build Environment",
            on_setup_scene=self.setup_scene,
            on_generate_objects=self.generate_objects,
            on_clear_objects=self.clear_objects,
            on_spawn_jetbot=self.spawn_jetbot_with_realsense,
        )
        self.ui_builder.show_window()

    def on_shutdown(self):
        """Method called when the extension is disabled"""
        carb.log_info(f"on_shutdown")

        self._stop_ros2_node()
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

    def spawn_jetbot_with_realsense(self):
        """Spawn a Jetbot and attach a RealSense D455 under its chassis in one undo group."""
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            carb.log_error("No open USD stage to spawn Jetbot on.")
            return

        # ensure /world stage path existing
        self._ensure_world_root(stage)

        jetbot_path = Sdf.Path("/World/Jetbot")
        if stage.GetPrimAtPath(jetbot_path):
            carb.log_warn("Spawn skipped because /World/Jetbot already exists.")
            return

        assets_root = get_assets_root_path()
        if assets_root is None:
            carb.log_error("Could not find Isaac Sim assets root.")
            return

        jetbot_asset = assets_root + "/Isaac/Robots/NVIDIA/Jetbot/jetbot.usd"
        realsense_asset = assets_root + "/Isaac/Sensors/Intel/RealSense/rsd455.usd"

        sensor_path = Sdf.Path(self._REALSENSE_SENSOR_PATH)

        # Reference both assets and apply the sensor offset inside a single undo group so
        # the whole robot setup can be reverted in one step.
        with omni.kit.undo.group():
            add_reference_to_stage(usd_path=jetbot_asset, prim_path=str(jetbot_path))

            if not stage.GetPrimAtPath(Sdf.Path("/World/Jetbot/chassis")):
                carb.log_error("Jetbot was created, but /World/Jetbot/chassis was not found for sensor attachment.")
                return

            add_reference_to_stage(usd_path=realsense_asset, prim_path=str(sensor_path))

            sensor_prim = stage.GetPrimAtPath(sensor_path)
            if not sensor_prim:
                carb.log_error("RealSense sensor reference was not created successfully.")
                return

            sensor_xform = UsdGeom.Xformable(sensor_prim)
            sensor_xform.ClearXformOpOrder()
            sensor_translate = sensor_xform.AddTranslateOp()
            sensor_translate.Set(Gf.Vec3d(0.05, 0.0, 0.08))

        # ROS 2 update: build the RealSense publishing graph right after the sensor is mounted.
        self._setup_realsense_ros2_publishers(stage, sensor_path)
        carb.log_info(f"Spawned Jetbot at {jetbot_path} with RealSense D455 at {sensor_path}.")

    def _setup_realsense_ros2_publishers(self, stage, sensor_path):
        """Create ROS 2 publishers for the mounted RealSense RGB and depth sensors."""
        ros2_modules = self._import_ros2_modules()
        if ros2_modules is None:
            return

        og, rep = ros2_modules
        camera_prims = self._find_realsense_camera_prims(stage, sensor_path)
        color_camera = self._pick_camera_prim(camera_prims, preferred_tokens=("color", "rgb", "left"))
        depth_camera = self._pick_camera_prim(camera_prims, preferred_tokens=("depth",))

        if color_camera is None and depth_camera is None:
            carb.log_error(
                f"No UsdGeom.Camera prims were found below {sensor_path}; ROS 2 publishers were not created."
            )
            return

        render_products = {}
        publishers = []

        # ROS 2 update: publish the RGB stream and matching camera info when a color camera exists.
        if color_camera is not None:
            color_render_product = self._create_render_product(rep, color_camera.GetPath())
            if color_render_product is not None:
                render_products["color"] = color_render_product
                publishers.extend(
                    (
                        {
                            "node_name": "ColorImagePublisher",
                            "type": "rgb",
                            "topic_name": "camera/color/image_raw",
                            "frame_id": "realsense_color_frame",
                            "render_product_path": color_render_product,
                        },
                        {
                            "node_name": "ColorCameraInfoPublisher",
                            "type": "camera_info",
                            "topic_name": "camera/color/camera_info",
                            "frame_id": "realsense_color_frame",
                            "render_product_path": color_render_product,
                        },
                    )
                )

        # ROS 2 update: publish the depth stream and matching camera info when a depth camera exists.
        if depth_camera is not None:
            depth_render_product = self._create_render_product(rep, depth_camera.GetPath())
            if depth_render_product is not None:
                render_products["depth"] = depth_render_product
                publishers.extend(
                    (
                        {
                            "node_name": "DepthImagePublisher",
                            "type": "depth",
                            "topic_name": "camera/depth/image_rect_raw",
                            "frame_id": "realsense_depth_frame",
                            "render_product_path": depth_render_product,
                        },
                        {
                            "node_name": "DepthCameraInfoPublisher",
                            "type": "camera_info",
                            "topic_name": "camera/depth/camera_info",
                            "frame_id": "realsense_depth_frame",
                            "render_product_path": depth_render_product,
                        },
                    )
                )

        if not publishers:
            carb.log_error("RealSense camera render products could not be created; ROS 2 publishers were not created.")
            return

        if not self._build_realsense_ros2_graph(stage, og, publishers):
            return

        published_topics = ", ".join(publisher["topic_name"] for publisher in publishers)
        carb.log_info(f"Publishing RealSense ROS 2 topics from {sensor_path}: {published_topics}")

    def _import_ros2_modules(self):
        """Load the modules needed to create ROS 2 camera publishers."""
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        # ROS 2 update: this extension uses Isaac Sim bridge-managed publishers instead of a manual rclpy node.
        # ROS 2 update: these extensions must be enabled before creating the camera helper nodes.
        required_extensions = (
            "omni.graph.action",
            "omni.isaac.core_nodes",
            "isaacsim.ros2.bridge",
            "omni.replicator.core",
        )
        for extension_name in required_extensions:
            if not extension_manager.is_extension_enabled(extension_name):
                extension_manager.set_extension_enabled_immediate(extension_name, True)

        try:
            import omni.graph.core as og
            import omni.replicator.core as rep
        except Exception as exc:
            carb.log_error(f"Failed to import Isaac Sim ROS 2 publishing modules: {exc}")
            return None

        return og, rep

    def _start_ros2_node(self):
        """Create a lightweight ROS 2 node for this extension if rclpy is available."""
        if self._ros2_node is not None:
            return self._ros2_node

        try:
            import rclpy
            from rclpy.context import Context
        except Exception as exc:
            carb.log_warn(f"ROS 2 node startup skipped because rclpy is unavailable: {exc}")
            return None

        try:
            context = Context()
            rclpy.init(args=None, context=context)
            node = rclpy.create_node("ncume_cps_slam_extension", context=context)
        except Exception as exc:
            carb.log_error(f"Failed to start ROS 2 node for this extension: {exc}")
            return None

        self._ros2_context = context
        self._ros2_node = node
        carb.log_info("Started ROS 2 node 'ncume_cps_slam_extension'.")
        return node

    def _stop_ros2_node(self):
        """Destroy the extension ROS 2 node and shut down its context."""
        context = getattr(self, "_ros2_context", None)
        node = getattr(self, "_ros2_node", None)

        if node is not None:
            try:
                node.destroy_node()
            except Exception as exc:
                carb.log_warn(f"Failed to destroy ROS 2 node cleanly: {exc}")

        if context is not None:
            try:
                import rclpy

                if context.ok():
                    rclpy.shutdown(context=context)
            except Exception as exc:
                carb.log_warn(f"Failed to shut down ROS 2 context cleanly: {exc}")

        self._ros2_node = None
        self._ros2_context = None

    def _find_realsense_camera_prims(self, stage, sensor_path):
        """Return every camera prim nested below the mounted RealSense asset."""
        sensor_prim = stage.GetPrimAtPath(sensor_path)
        if not sensor_prim:
            return []

        camera_prims = []
        prim_stack = [sensor_prim]
        while prim_stack:
            prim = prim_stack.pop()
            if prim.IsA(UsdGeom.Camera):
                camera_prims.append(prim)
            prim_stack.extend(reversed(list(prim.GetChildren())))

        return camera_prims

    def _pick_camera_prim(self, camera_prims, preferred_tokens):
        """Choose the best camera prim by matching tokens in the prim path."""
        if not camera_prims:
            return None

        for prim in camera_prims:
            prim_path = str(prim.GetPath()).lower()
            if any(token in prim_path for token in preferred_tokens):
                return prim

        return camera_prims[0]

    def _create_render_product(self, rep, camera_prim_path, resolution=(640, 480)):
        """Create a render product for a camera prim and return its USD path."""
        try:
            render_product = rep.create.render_product(str(camera_prim_path), resolution=resolution)
        except Exception as exc:
            carb.log_error(f"Failed to create render product for {camera_prim_path}: {exc}")
            return None

        render_product_path = getattr(render_product, "path", render_product)
        if not render_product_path:
            carb.log_error(f"Render product creation for {camera_prim_path} returned an empty path.")
            return None

        return str(render_product_path)

    def _build_realsense_ros2_graph(self, stage, og, publishers):
        """Build an OmniGraph that publishes the requested RealSense topics over ROS 2."""
        graph_path = self._ROS2_GRAPH_PATH
        graph_prim = stage.GetPrimAtPath(graph_path)
        if graph_prim:
            stage.RemovePrim(graph_path)

        keys = og.Controller.Keys
        create_nodes = [("OnPlaybackTick", "omni.graph.action.OnPlaybackTick")]
        connect = []
        set_values = []

        # ROS 2 update: select the Isaac Sim bridge node type that matches each message kind.
        for publisher in publishers:
            node_name = publisher["node_name"]
            node_type = "isaacsim.ros2.bridge.ROS2CameraHelper"
            if publisher["type"] == "camera_info":
                node_type = "isaacsim.ros2.bridge.ROS2CameraInfoHelper"

            create_nodes.append((node_name, node_type))
            connect.append(("OnPlaybackTick.outputs:tick", f"{node_name}.inputs:execIn"))
            publisher_values = [
                (f"{node_name}.inputs:topicName", publisher["topic_name"]),
                (f"{node_name}.inputs:frameId", publisher["frame_id"]),
                (f"{node_name}.inputs:renderProductPath", publisher["render_product_path"]),
            ]
            if publisher["type"] != "camera_info":
                publisher_values.append((f"{node_name}.inputs:type", publisher["type"]))
            set_values.extend(publisher_values)

        try:
            og.Controller.edit(
                {"graph_path": graph_path, "evaluator_name": "execution"},
                {
                    keys.CREATE_NODES: create_nodes,
                    keys.CONNECT: connect,
                    keys.SET_VALUES: set_values,
                },
            )
        except Exception as exc:
            carb.log_error(f"Failed to create the RealSense ROS 2 publishing graph at {graph_path}: {exc}")
            return False

        return True

    def _ensure_scene_root(self, stage):
        """Ensure the extension scene root exists and return its path."""
        self._ensure_world_root(stage)

        scene_root = Sdf.Path("/World/BuildEnvironment")
        if not stage.GetPrimAtPath(scene_root):
            UsdGeom.Xform.Define(stage, scene_root)

        return scene_root

    def _ensure_world_root(self, stage):
        """Ensure the stage has a /World Xform root."""
        world_path = Sdf.Path("/World")
        if not stage.GetPrimAtPath(world_path):
            UsdGeom.Xform.Define(stage, world_path)
        return world_path

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
