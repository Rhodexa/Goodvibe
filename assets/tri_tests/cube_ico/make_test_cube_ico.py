import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.frame_start, sc.frame_end = 1, 8
sc.render.resolution_x, sc.render.resolution_y = 480, 360
def mat(name, rgb):
    m = bpy.data.materials.new(name)
    try: m.use_nodes = True
    except Exception: pass
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1)
    return m
bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.object; cube.data.materials.append(mat("red", (0.8, 0.05, 0.05)))
cube.rotation_euler = (0, 0, 0); cube.keyframe_insert("rotation_euler", frame=1)
cube.rotation_euler = (0.5, 0.3, math.pi/2); cube.keyframe_insert("rotation_euler", frame=9)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.1, location=(0.9, 0.3, 0.6))
ico = bpy.context.object; ico.data.materials.append(mat("blue", (0.05, 0.2, 0.8)))
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.5))
bpy.context.object.data.materials.append(mat("green", (0.1, 0.5, 0.1)))
bpy.ops.object.camera_add(location=(0, -6, 1.5), rotation=(math.radians(80), 0, 0))
sc.camera = bpy.context.object
bpy.ops.object.light_add(type="SUN", rotation=(0.6, 0.3, 0.2)); bpy.context.object.data.energy = 3
w = bpy.data.worlds.new("w"); sc.world = w
