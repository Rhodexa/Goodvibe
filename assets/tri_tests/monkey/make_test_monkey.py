import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
sc.render.engine = "BLENDER_EEVEE"
sc.frame_start, sc.frame_end = 1, 24
sc.render.resolution_x, sc.render.resolution_y = 480, 360
def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1)
    return m
def spin(ob, axis, turns):
    for f, a in ((1, 0), (25, turns * 2 * math.pi)):
        r = list(ob.rotation_euler); r[axis] = a; ob.rotation_euler = r
        ob.keyframe_insert("rotation_euler", index=axis, frame=f)
    for layer in ob.animation_data.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for k in fc.keyframe_points: k.interpolation = "LINEAR"
bpy.ops.mesh.primitive_monkey_add(size=2.2, location=(0, 0, 0.2))
monkey = bpy.context.object
dec = monkey.modifiers.new("dec", "DECIMATE"); dec.ratio = 0.3
monkey.data.materials.append(mat("orange", (0.9, 0.35, 0.05)))
spin(monkey, 2, 1)
bpy.ops.object.empty_add(location=(0, 0, 0.2)); pivot = bpy.context.object
pivot.rotation_euler = (math.radians(25), 0, 0)
bpy.ops.mesh.primitive_torus_add(major_radius=0.45, minor_radius=0.14, major_segments=14, minor_segments=6, location=(2.0, 0, 0))
torus = bpy.context.object; torus.data.materials.append(mat("teal", (0.05, 0.55, 0.6)))
torus.parent = pivot
spin(pivot, 2, 1)
spin(torus, 0, 2)
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -1.2))
bpy.context.object.data.materials.append(mat("purple", (0.25, 0.12, 0.35)))
bpy.ops.object.camera_add(location=(0, -6.5, 2.2), rotation=(math.radians(75), 0, 0))
sc.camera = bpy.context.object
bpy.ops.object.light_add(type="SUN", rotation=(0.7, 0.2, 0.5)); bpy.context.object.data.energy = 3.5
w = bpy.data.worlds.new("w"); sc.world = w
