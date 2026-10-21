"""Dirt/distance driven object material integration for Maya / V-Ray.

Run in Maya's Python Script Editor. No external Python dependencies.
Target: Maya 2026, V-Ray 7.x. Runtime/render validation is required.
"""
import json
import traceback
import maya.cmds as c

WINDOW = 'vrayObjectBlendWindow'


def attr(node, *names):
    for name in names:
        if c.objExists(node + '.' + name):
            return node + '.' + name
    raise RuntimeError('Unsupported V-Ray node layout: %s; expected %s. Available: %s'
                       % (node, names, ', '.join(c.listAttr(node) or [])))


def wire(source, target):
    c.connectAttr(source, target, force=True)


def rgb(plug, value):
    c.setAttr(plug, value, value, value, type='double3')


def mesh(transform):
    shapes = c.listRelatives(transform, shapes=True, noIntermediate=True,
                             fullPath=True) or []
    shapes = [s for s in shapes if c.nodeType(s) in ('mesh', 'VRayProxy')]
    if len(shapes) != 1:
        raise RuntimeError('Exactly one mesh or V-Ray proxy shape is required: ' + transform)
    if len(c.listRelatives(shapes[0], allParents=True) or []) != 1:
        raise RuntimeError('Instanced meshes are not supported: ' + transform)
    return shapes[0]


def object_transform(node):
    if c.nodeType(node) in ('mesh', 'VRayProxy'):
        node = c.listRelatives(node, parent=True, fullPath=True)[0]
    node = c.ls(node, long=True)[0]
    mesh(node)
    return node


def uv_status(obj):
    """Inspect the active mesh UV set. Never infer proxy UVs from its preview."""
    shape = mesh(obj)
    if c.nodeType(shape) == 'VRayProxy':
        return 'UV ?', 'Proxy UVs are not verified. The viewport preview does not prove the render geometry has UVs.'
    try:
        import maya.api.OpenMaya as om
        selection = om.MSelectionList(); selection.add(shape)
        fn = om.MFnMesh(selection.getDagPath(0))
        uv_set = fn.currentUVSetName()
        if not uv_set or fn.numUVs(uv_set) == 0:
            return 'NO UV', 'No UVs in the current UV set. UV-based color and displacement maps may be incorrect; world-space/triplanar maps may still work.'
        counts, ids = fn.getAssignedUVs(uv_set)
        missing = sum(1 for count in counts if count == 0)
        if missing:
            return 'PARTIAL', '%d of %d faces have no UV assignment in %s.' % (missing, fn.numPolygons, uv_set)
        return 'UV OK', 'Current UV set: %s. Assignment exists; layout quality and other UV sets are not validated.' % uv_set
    except RuntimeError as exc:
        return 'UV ?', 'UV check unavailable: ' + str(exc)




def bindings(transform):
    """Return SG assignment or individual modern proxy shader connections.

    Existing hierarchy/custom rule names and priority remain unchanged.
    No material nodes shared by other proxies are edited.
    """
    shape = mesh(transform)
    if c.nodeType(shape) != 'VRayProxy':
        sg, mat = material(transform)
        return [dict(obj=transform, sg=sg, mat=mat, kind='sg')]
    groups = list(set(c.listConnections(shape, type='shadingEngine') or []))
    overrides = [sg for sg in groups if sg != 'initialShadingGroup']
    if overrides:
        sg, mat = material(transform)
        return [dict(obj=transform, sg=sg, mat=mat, kind='sg')]
    if (c.attributeQuery('materialAssignmentsFile', node=shape, exists=True)
            and c.getAttr(shape + '.materialAssignmentsFile')):
        raise RuntimeError('This proxy uses an external material assignment file. '
                           'Use local connected materials or a whole-object V-Ray material override: '
                           + transform)
    result = []
    for array, child in [('shaders', 'shadersConnections'),
                         ('shadersCustom', 'shadersCustomConnections')]:
        for index in c.getAttr(shape + '.' + array, multiIndices=True) or []:
            suffix = '%s[%d].%s' % (array, index, child)
            plug = shape + '.' + suffix
            source = c.connectionInfo(plug, sourceFromDestination=True)
            if not source:
                continue
            mat, output = source.split('.', 1)
            if not c.nodeType(mat).startswith('VRay'):
                raise RuntimeError('Proxy slot requires a V-Ray material: ' + plug)
            if c.getAttr(plug, lock=True):
                raise RuntimeError('Proxy material slot is locked: ' + plug)
            result.append(dict(obj=transform, mat=mat, sg=None, kind='proxy',
                               shape=shape, destination=suffix, output=output))
    if not result:
        raise RuntimeError('Proxy has no connected local V-Ray materials. Connect its '
                           'material slots or assign a V-Ray material: ' + transform)
    return result


def material(transform):
    shape = mesh(transform)
    groups = list(set(c.listConnections(shape, type='shadingEngine') or []))
    if len(groups) != 1:
        raise RuntimeError('Assign one material to the whole object first: ' + transform)
    sg = groups[0]
    mats = c.listConnections(sg + '.surfaceShader', source=True, destination=False) or []
    if len(mats) != 1 or not c.nodeType(mats[0]).startswith('VRay'):
        raise RuntimeError('A V-Ray material is required: ' + transform)
    return sg, mats[0]


def link_role(rig, role, node):
    c.addAttr(rig, longName=role, attributeType='message')
    wire(node + '.message', rig + '.' + role)


def role(rig, name):
    nodes = c.listConnections(rig + '.' + name, source=True, destination=False) or []
    if not nodes:
        raise RuntimeError('Missing setup node: ' + name)
    return nodes[0]


def rigs():
    return [n for n in c.ls(type='network') or [] if c.attributeQuery('objectBlendVersion', node=n, exists=True)]


def number(rig, name, default, low=None, high=None):
    options = dict(longName=name, attributeType='double', defaultValue=default, keyable=True)
    if low is not None:
        options['minValue'] = low
    if high is not None:
        options['maxValue'] = high
    c.addAttr(rig, **options)


def install_dirt(rig):
    """Add the material-mask branch; retain distance-based displacement."""
    if c.attributeQuery('dirtTexture', node=rig, exists=True):
        return
    preview_mat = role(rig, 'previewMaterial')
    def upstream(plug, expected):
        nodes = c.listConnections(plug, source=True, destination=False) or []
        if len(nodes) != 1 or c.nodeType(nodes[0]) != expected:
            raise RuntimeError('Cannot upgrade an edited mask graph: ' + plug)
        return nodes[0]
    old_strength = upstream(preview_mat + '.outColor', 'multiplyDivide')
    old_power = upstream(old_strength + '.input1', 'multiplyDivide')
    old_product = upstream(old_power + '.input1', 'multiplyDivide')
    noise = upstream(old_product + '.input2', 'blendColors')
    dist = role(rig, 'distanceTexture')
    dirt = c.shadingNode('VRayDirt', asTexture=True, name='OB_dirt#')
    link_role(rig, 'dirtTexture', dirt)
    # White in occluded areas so the ground coat appears in the contacts.
    rgb(attr(dirt, 'blackColor'), 1)
    rgb(attr(dirt, 'whiteColor'), 0)
    c.setAttr(attr(dirt, 'radius'), c.getAttr(rig + '.distance'))
    c.setAttr(attr(dirt, 'occlusionMode'), 0)
    c.setAttr(attr(dirt, 'considerSameObjectOnly'), False)
    c.setAttr(attr(dirt, 'ignoreSelfOcclusion'), True)
    c.setAttr(attr(dirt, 'ignoreBump'), True)
    c.setAttr(attr(dirt, 'ignoreForGi'), False)
    c.addAttr(rig, longName='dirtGroundOnly', attributeType='bool', defaultValue=True)
    wire(role(rig, 'distanceObjects') + '.message', attr(dirt, 'resultAffect'))
    c.setAttr(attr(dirt, 'resultAffectInclusive'), True)
    c.addAttr(rig, longName='maskMode', attributeType='enum',
              enumName='Dirt:Distance:Distance x Dirt', keyable=True)
    both = c.shadingNode('multiplyDivide', asUtility=True, name='OB_distanceTimesDirt#')
    wire(dist + '.outColor', both + '.input1')
    wire(dirt + '.outColor', both + '.input2')
    distance_choice = c.shadingNode('condition', asUtility=True, name='OB_distanceChoice#')
    wire(rig + '.maskMode', distance_choice + '.firstTerm')
    c.setAttr(distance_choice + '.secondTerm', 1)
    wire(dist + '.outColor', distance_choice + '.colorIfTrue')
    wire(both + '.output', distance_choice + '.colorIfFalse')
    selector = c.shadingNode('condition', asUtility=True, name='OB_maskSelector#')
    wire(rig + '.maskMode', selector + '.firstTerm')
    c.setAttr(selector + '.secondTerm', 0)
    wire(dirt + '.outColor', selector + '.colorIfTrue')
    wire(distance_choice + '.outColor', selector + '.colorIfFalse')
    product = c.shadingNode('multiplyDivide', asUtility=True, name='OB_materialMaskNoise#')
    wire(selector + '.outColor', product + '.input1')
    wire(noise + '.output', product + '.input2')
    power = c.shadingNode('multiplyDivide', asUtility=True, name='OB_materialMaskFalloff#')
    c.setAttr(power + '.operation', 3)
    wire(product + '.output', power + '.input1')
    strength = c.shadingNode('multiplyDivide', asUtility=True, name='OB_materialMaskStrength#')
    wire(power + '.output', strength + '.input1')
    for axis in 'XYZ':
        wire(rig + '.falloff', power + '.input2' + axis)
        wire(rig + '.strength', strength + '.input2' + axis)
    link_role(rig, 'materialMask', strength)
    link_role(rig, 'maskSelector', selector)
    link_role(rig, 'displacementMask', old_strength)
    for record in json.loads(c.getAttr(rig + '.records')):
        blend = role(rig, 'blendMaterial%d' % record['index'])
        wire(strength + '.output', attr(blend, 'coat_materials[0].blend_amount',
                                        'blend_amount_0', 'blendAmount0', 'blend_amount[0]'))
    wire(strength + '.output', preview_mat + '.outColor')
    c.setAttr(rig + '.objectBlendVersion', '1.2', type='string')


def upgrade_dirt(rig):
    if not c.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya Undo before upgrading.')
    if c.attributeQuery('dirtTexture', node=rig, exists=True):
        return
    c.undoInfo(openChunk=True, chunkName='Add Object Blend Dirt control')
    try:
        install_dirt(rig)
    except Exception:
        c.undoInfo(closeChunk=True)
        c.undo()
        raise
    else:
        c.undoInfo(closeChunk=True)


def dirt_scope(rig, ground_only):
    dirt = role(rig, 'dirtTexture')
    plug = dirt + '.resultAffect'
    c.undoInfo(openChunk=True, chunkName='Object Blend Dirt scope')
    try:
        for source in c.listConnections(plug, source=True, destination=False, plugs=True) or []:
            c.disconnectAttr(source, plug)
        if ground_only:
            wire(role(rig, 'distanceObjects') + '.message', plug)
        c.setAttr(dirt + '.resultAffectInclusive', bool(ground_only))
        c.setAttr(rig + '.dirtGroundOnly', bool(ground_only))
    finally:
        c.undoInfo(closeChunk=True)


def build(objects, ground, _manage_undo=True):
    if not c.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya Undo before building this setup.')
    if not c.pluginInfo('vrayformaya', query=True, loaded=True):
        c.loadPlugin('vrayformaya')
    objects = list(dict.fromkeys(object_transform(obj) for obj in objects))
    ground = object_transform(ground)
    if ground not in objects:
        raise RuntimeError('Ground must be one of the loaded objects.')
    targets = [obj for obj in objects if obj != ground]
    if not targets:
        raise RuntimeError('Load at least two meshes or V-Ray proxies.')
    ground_materials = {binding['mat'] for binding in bindings(ground)}
    if len(ground_materials) != 1:
        raise RuntimeError('The ground/source must have one material; target proxies may have many.')
    ground_mat = ground_materials.pop()
    originals = [binding for obj in targets for binding in bindings(obj)]
    for obj in objects:
        if c.referenceQuery(obj, isNodeReferenced=True):
            raise RuntimeError('Use local, editable objects: ' + obj)
    # Do not silently stack multiple managed setups on the same targets.
    used = {c.ls(obj, uuid=True)[0] for obj in targets}
    for existing in rigs():
        if c.getAttr(existing + '.active'):
            records = json.loads(c.getAttr(existing + '.records'))
            if any(record['uuid'] in used for record in records):
                raise RuntimeError('Some objects already have an active Object Blend setup.')
    if _manage_undo:
        c.undoInfo(openChunk=True, chunkName='Build V-Ray Object Blend')
    rig = None
    try:
        rig = c.createNode('network', name='ObjectBlend_SETUP#')
        c.addAttr(rig, longName='objectBlendVersion', dataType='string')
        c.setAttr(rig + '.objectBlendVersion', '1.1', type='string')
        c.addAttr(rig, longName='active', attributeType='bool', defaultValue=True)
        for name, default, low, high in [('distance', 10, .0001, None),
                ('strength', 1, 0, 1), ('falloff', 1, .01, 10),
                ('noiseAmount', 0, 0, 1), ('noiseFrequency', 1, .001, None),
                ('noiseScale', 1, .001, None),
                ('contactDisplacement', 0, None, None)]:
            number(rig, name, default, low, high)
        c.addAttr(rig, longName='maskPreview', attributeType='bool')
        dist = c.shadingNode('VRayDistanceTex', asTexture=True, name='OB_distance#')
        link_role(rig, 'distanceTexture', dist)
        wire(rig + '.distance', attr(dist, 'distance', 'radius'))
        rgb(attr(dist, 'nearColor', 'near_color'), 1)
        rgb(attr(dist, 'farColor', 'far_color'), 0)
        object_plug = attr(dist, 'objects')
        sets = c.listConnections(object_plug, source=True, destination=False, type='objectSet') or []
        if sets:
            distance_set = sets[0]
        else:
            distance_set = c.sets(empty=True, name='OB_distanceObjects#')
            if c.getAttr(object_plug, type=True) != 'message':
                raise RuntimeError('Unexpected VRayDistanceTex.objects type; setup rolled back.')
            if c.attributeQuery('objects', node=dist, multi=True):
                object_plug += '[0]'
            wire(distance_set + '.message', object_plug)
        c.sets(ground, addElement=distance_set)
        link_role(rig, 'distanceObjects', distance_set)
        # Shared world-space noise: object UVs are not needed for the mask.
        noise = c.shadingNode('solidFractal', asTexture=True, name='OB_noise#')
        place = c.shadingNode('place3dTexture', asUtility=True, name='OB_noisePlacement#')
        wire(place + '.worldInverseMatrix[0]', noise + '.placementMatrix')
        for axis in 'XYZ':
            wire(rig + '.noiseScale', place + '.scale' + axis)
        wire(rig + '.noiseFrequency', noise + '.frequencyRatio')
        link_role(rig, 'noiseTexture', noise)
        link_role(rig, 'noisePlacement', place)
        noise_mix = c.shadingNode('blendColors', asUtility=True, name='OB_noiseWeight#')
        wire(noise + '.outColor', noise_mix + '.color1')
        rgb(noise_mix + '.color2', 1)
        wire(rig + '.noiseAmount', noise_mix + '.blender')
        product = c.shadingNode('multiplyDivide', asUtility=True, name='OB_maskProduct#')
        wire(dist + '.outColor', product + '.input1')
        wire(noise_mix + '.output', product + '.input2')
        power = c.shadingNode('multiplyDivide', asUtility=True, name='OB_falloff#')
        c.setAttr(power + '.operation', 3)
        wire(product + '.output', power + '.input1')
        for axis in 'XYZ':
            wire(rig + '.falloff', power + '.input2' + axis)
        strength = c.shadingNode('multiplyDivide', asUtility=True, name='OB_strength#')
        wire(power + '.output', strength + '.input1')
        for axis in 'XYZ':
            wire(rig + '.strength', strength + '.input2' + axis)
        preview = c.shadingNode('surfaceShader', asShader=True, name='OB_maskPreview#')
        wire(strength + '.output', preview + '.outColor')
        link_role(rig, 'previewMaterial', preview)
        records = []
        for index, binding in enumerate(originals):
            obj, original_sg, original_mat = binding['obj'], binding['sg'], binding['mat']
            blend = c.shadingNode('VRayBlendMtl', asShader=True, name='OB_blend#')
            wire(original_mat + '.' + binding.get('output', 'outColor'), attr(blend, 'base_material', 'baseMaterial'))
            wire(ground_mat + '.outColor', attr(blend, 'coat_materials[0].coat_material', 'coat_material_0', 'coatMaterial0', 'coat_material[0]'))
            wire(strength + '.output', attr(blend, 'coat_materials[0].blend_amount', 'blend_amount_0', 'blendAmount0', 'blend_amount[0]'))
            for name in ('additive_mode', 'additiveMode'):
                if c.attributeQuery(name, node=blend, exists=True):
                    c.setAttr(blend + '.' + name, False)
            link_role(rig, 'target%d' % index, obj)
            link_role(rig, 'blendMaterial%d' % index, blend)
            record = {'uuid': c.ls(obj, uuid=True)[0], 'index': index, 'kind': binding['kind']}
            if binding['kind'] == 'proxy':
                link_role(rig, 'proxyShape%d' % index, binding['shape'])
                link_role(rig, 'originalMaterial%d' % index, original_mat)
                record.update(destination=binding['destination'], output=binding['output'])
                wire(blend + '.outColor', binding['shape'] + '.' + binding['destination'])
                records.append(record)
                continue
            sg = c.sets(renderable=True, noSurfaceShader=True, empty=True, name='OB_blendSG#')
            wire(blend + '.outColor', sg + '.surfaceShader')
            original_disp = c.listConnections(original_sg + '.displacementShader',
                                               source=True, destination=False, plugs=True) or []
            contact = c.shadingNode('multDoubleLinear', asUtility=True, name='OB_contactHeight#')
            wire(strength + '.outputX', contact + '.input1')
            wire(rig + '.contactDisplacement', contact + '.input2')
            total = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_displacementSum#')
            wire(contact + '.output', total + '.input1')
            if original_disp:
                wire(original_disp[0], total + '.input2')
            displacement = c.shadingNode('displacementShader', asShader=True, name='OB_displacement#')
            wire(total + '.output', displacement + '.displacement')
            wire(displacement + '.displacement', sg + '.displacementShader')
            link_role(rig, 'originalSG%d' % index, original_sg)
            link_role(rig, 'blendSG%d' % index, sg)
            records.append(record)
            c.sets(obj, edit=True, forceElement=sg)
        c.addAttr(rig, longName='records', dataType='string')
        c.setAttr(rig + '.records', json.dumps(records), type='string')
        install_dirt(rig)
        c.setAttr(rig + '.maskMode', 1)  # New objects start in Distance mode.
        c.setAttr(rig + '.objectBlendVersion', '1.3', type='string')
        c.select(rig)
    except Exception:
        if _manage_undo:
            c.undoInfo(closeChunk=True)
            if rig is not None:
                c.undo()
        raise
    else:
        if _manage_undo:
            c.undoInfo(closeChunk=True)
    return rig


def preview(rig, enabled):
    records = json.loads(c.getAttr(rig + '.records'))
    connections = []
    for record in records:
        i = record['index']
        shader = role(rig, 'previewMaterial' if enabled else 'blendMaterial%d' % i)
        if (not enabled and c.objExists(rig + '.proxyDisplacementMaterial%d' % i)
                and c.getAttr(rig + '.blendGroundDisplacement')):
            shader = role(rig, 'proxyDisplacementMaterial%d' % i)
        destination = (role(rig, 'proxyShape%d' % i) + '.' + record['destination']
                       if record.get('kind') == 'proxy' else
                       role(rig, 'blendSG%d' % i) + '.surfaceShader')
        connections.append((shader + '.outColor', destination))
    c.undoInfo(openChunk=True, chunkName='Object Blend preview')
    try:
        for source, destination in connections:
            wire(source, destination)
        c.setAttr(rig + '.maskPreview', enabled)
    finally:
        c.undoInfo(closeChunk=True)


def restore(rig):
    records = json.loads(c.getAttr(rig + '.records'))
    assignments, connections = [], []
    for record in records:
        i = record['index']
        if record.get('kind') == 'proxy':
            connections.append((role(rig, 'originalMaterial%d' % i) + '.' + record['output'],
                                role(rig, 'proxyShape%d' % i) + '.' + record['destination']))
        else:
            assignments.append((role(rig, 'target%d' % i), role(rig, 'originalSG%d' % i)))
    c.undoInfo(openChunk=True, chunkName='Restore Object Blend materials')
    try:
        for obj, sg in assignments:
            c.sets(obj, edit=True, forceElement=sg)
        for source, destination in connections:
            wire(source, destination)
        c.setAttr(rig + '.active', False)
        if c.objExists(rig + '.viewportGuides'):
            c.setAttr(role(rig, 'viewportGuides') + '.visibility', False)
    finally:
        c.undoInfo(closeChunk=True)


MODE_LABELS = {1: 'Distance', 0: 'Dirt', 2: 'Distance + Dirt'}
SETTING_NAMES = ('distance', 'strength', 'falloff', 'noiseAmount', 'noiseFrequency',
                 'noiseScale', 'contactDisplacement', 'maskMode')
DIRT_NAMES = ('radius', 'radiusMultiplier', 'distribution', 'falloff', 'subdivs',
              'biasX', 'biasY', 'biasZ', 'ignoreSelfOcclusion', 'ignoreBump',
              'doubleSided', 'considerSameObjectOnly', 'ignoreForGi', 'occlusionMode',
              'invertNormal', 'workWithTransparency', 'environmentOcclusion',
              'thinMode', 'blackColor', 'whiteColor')


def atomic(label, action):
    if not c.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya Undo first.')
    c.undoInfo(openChunk=True, chunkName=label)
    started = False
    try:
        # An empty failed chunk must never undo the user's preceding action.
        marker = c.createNode('network', name='OB_transactionGuard#', skipSelect=True)
        started = True
        c.delete(marker)
        result = action()
    except Exception:
        c.undoInfo(closeChunk=True)
        if started:
            c.undo()
        raise
    else:
        c.undoInfo(closeChunk=True)
        return result


def collections():
    return [n for n in c.ls(type='network') or []
            if c.attributeQuery('objectBlendCollection', node=n, exists=True)]


def members(collection):
    return sorted([n for n in c.listConnections(collection + '.members',
                    source=True, destination=False) or []
                   if c.objExists(n + '.active') and c.getAttr(n + '.active')])


def collection_link(collection, rig):
    indices = c.getAttr(collection + '.members', multiIndices=True) or []
    index = max(indices, default=-1) + 1
    wire(rig + '.message', '%s.members[%d]' % (collection, index))
    link_role(rig, 'collectionParent', collection)


def make_collection(ground):
    node = c.createNode('network', name='ObjectBlend_LIST#')
    c.addAttr(node, longName='objectBlendCollection', dataType='string')
    c.setAttr(node + '.objectBlendCollection', '1.3', type='string')
    c.addAttr(node, longName='members', attributeType='message', multi=True)
    link_role(node, 'ground', ground)
    return node


def add_objects(collection, objects, ground=None):
    """Append independent per-object setups atomically; duplicate selections are no-ops."""
    objects = list(dict.fromkeys(object_transform(obj) for obj in objects))
    ground = object_transform(role(collection, 'ground') if collection else ground)
    existing = {r['uuid'] for child in members(collection)
                for r in json.loads(c.getAttr(child + '.records'))} if collection else set()
    objects = [obj for obj in objects if obj != ground and c.ls(obj, uuid=True)[0] not in existing]
    if not objects:
        if collection:
            return collection
        raise RuntimeError('Select at least one target other than the ground.')
    # Validate all assignments before building any of the selected objects.
    for obj in objects + [ground]:
        bindings(obj)
    def action():
        node = collection or make_collection(ground)
        for obj in objects:
            child = build([obj, ground], ground, _manage_undo=False)
            collection_link(node, child)
        return node
    return atomic('Add Object Blend targets', action)


def snapshot_settings(rig):
    values = {name: c.getAttr(rig + '.' + name) for name in SETTING_NAMES
              if c.objExists(rig + '.' + name)}
    values.setdefault('maskMode', 1)
    dirt_values = {}
    if c.objExists(rig + '.dirtTexture'):
        dirt = role(rig, 'dirtTexture')
        dirt_values = {name: c.getAttr(dirt + '.' + name) for name in DIRT_NAMES
                       if c.objExists(dirt + '.' + name)}
    return values, dirt_values


def copy_blend_settings(source, targets):
    """Copy mask settings only; each target keeps its own materials and ground links."""
    targets = list(dict.fromkeys(node for node in targets if node != source))
    values, dirt_values = snapshot_settings(source)
    values.pop('contactDisplacement', None)
    ground_only = c.getAttr(source + '.dirtGroundOnly')
    def apply():
        for target in targets:
            if not c.objExists(target) or not c.getAttr(target + '.active'):
                raise RuntimeError('Target blend setup is inactive or missing: ' + target)
            for name, value in values.items():
                c.setAttr(target + '.' + name, value)
            dirt = role(target, 'dirtTexture')
            for name, value in dirt_values.items():
                plug = dirt + '.' + name
                if not c.objExists(plug): continue
                if isinstance(value, (list, tuple)):
                    c.setAttr(plug, *value[0], type=c.getAttr(plug, type=True))
                else:
                    c.setAttr(plug, value)
            dirt_scope(target, ground_only)
        return len(targets)
    return atomic('Copy Distance Dirt settings', apply)


def remove_blend_targets(targets):
    targets = list(dict.fromkeys(targets))
    def apply():
        for target in targets: restore(target)
    return atomic('Remove Object Blend targets', apply)


def edit_collection(node):
    """Migrate a legacy shared setup, retaining each object's current look."""
    if node in collections():
        return node
    if c.objExists(node + '.collectionParent'):
        return role(node, 'collectionParent')
    ground_objects = c.sets(role(node, 'distanceObjects'), query=True) or []
    if len(ground_objects) != 1:
        raise RuntimeError('The old setup must have exactly one ground object to upgrade.')
    ground = object_transform(ground_objects[0])
    records = json.loads(c.getAttr(node + '.records'))
    targets = list(dict.fromkeys(role(node, 'target%d' % r['index']) for r in records))
    values, dirt_values = snapshot_settings(node)
    old_preview = c.getAttr(node + '.maskPreview')
    old_scope = c.getAttr(node + '.dirtGroundOnly') if c.objExists(node + '.dirtGroundOnly') else True
    def action():
        restore(node)
        collection = make_collection(ground)
        for target in targets:
            child = build([target, ground], ground, _manage_undo=False)
            for name, value in values.items():
                c.setAttr(child + '.' + name, value)
            dirt = role(child, 'dirtTexture')
            for name, value in dirt_values.items():
                if isinstance(value, list) and isinstance(value[0], tuple):
                    c.setAttr(dirt + '.' + name, *value[0], type='double3')
                else:
                    c.setAttr(dirt + '.' + name, value)
            dirt_scope(child, old_scope)
            if old_preview:
                preview(child, True)
            collection_link(collection, child)
        return collection
    return atomic('Upgrade to per-object blend settings', action)


def viewport_guides(rig, enabled):
    """Live radius reference rings at target pivot, NOT a rendered AO/falloff mask."""
    if c.objExists(rig + '.viewportGuides'):
        c.setAttr(role(rig, 'viewportGuides') + '.visibility', enabled)
        return
    if not enabled:
        return
    def action():
        target = role(rig, 'target0')
        group = c.createNode('transform', name='OB_viewportRadiusGuide#')
        link_role(rig, 'viewportGuides', group)
        c.pointConstraint(target, group, maintainOffset=False)
        for kind, driver, color, hidden_mode in (
                ('distance', rig + '.distance', (0.15, .75, 1), 0),
                ('dirt', role(rig, 'dirtTexture') + '.radius', (1, .55, .12), 1)):
            holder = c.createNode('transform', name='OB_' + kind + 'Radius#', parent=group)
            visibility = c.shadingNode('condition', asUtility=True, name='OB_guideVisibility#')
            c.setAttr(visibility + '.operation', 1)  # Not equal.
            c.setAttr(visibility + '.secondTerm', hidden_mode)
            c.setAttr(visibility + '.colorIfTrueR', 1)
            c.setAttr(visibility + '.colorIfFalseR', 0)
            wire(rig + '.maskMode', visibility + '.firstTerm')
            wire(visibility + '.outColorR', holder + '.visibility')
            for axis in 'XYZ':
                wire(driver, holder + '.scale' + axis)
            for normal in ((1,0,0), (0,1,0), (0,0,1)):
                curve = c.circle(normal=normal, radius=1, constructionHistory=False,
                                 name='OB_' + kind + 'RadiusRing#')[0]
                c.parent(curve, holder, relative=True)
                shape = c.listRelatives(curve, shapes=True)[0]
                c.setAttr(shape + '.overrideEnabled', True)
                c.setAttr(shape + '.overrideRGBColors', True)
                c.setAttr(shape + '.overrideColorRGB', *color, type='double3')
                c.setAttr(shape + '.overrideDisplayType', 2)
                for flag in ('primaryVisibility', 'castsShadows', 'receiveShadows',
                             'visibleInReflections', 'visibleInRefractions'):
                    if c.objExists(shape + '.' + flag):
                        c.setAttr(shape + '.' + flag, False)
        return group
    atomic('Show blend viewport radius guides', action)


# Color correction is separate from blend setup creation and works without a setup.
CC_CHANNELS = {'Color': 'diffuseColor', 'Roughness': 'reflectionGlossiness',
               'Emissive': 'illumColor'}


def _cc_input(source_plug, destination):
    """Copy a value and all incoming compound/child connections, without moving them."""
    value = c.getAttr(source_plug)
    source = c.connectionInfo(source_plug, sourceFromDestination=True)
    if source:
        wire(source, destination)
        return
    if isinstance(value, (tuple, list)):
        c.setAttr(destination, *value[0], type=c.getAttr(destination, type=True))
        node, name = source_plug.split('.', 1)
        dst_node, dst_name = destination.split('.', 1)
        children = c.attributeQuery(name, node=node, listChildren=True) or []
        dst_children = c.attributeQuery(dst_name, node=dst_node, listChildren=True) or []
        for child, dst_child in zip(children, dst_children):
            incoming = c.connectionInfo(node + '.' + child, sourceFromDestination=True)
            if incoming:
                wire(incoming, dst_node + '.' + dst_child)
    else:
        c.setAttr(destination, value)


def _cc_clone(material_node, channel, nodes, visited=None):
    """Copy only the material/base path; keep maps and blend coats connected."""
    visited = set(visited or ())
    if material_node in visited:
        raise RuntimeError('Cyclic material graph: ' + material_node)
    visited.add(material_node)
    kind = c.nodeType(material_node)
    if kind not in ('VRayMtl', 'VRayBlendMtl'):
        raise RuntimeError('Color correction supports VRayMtl or the base of VRayBlendMtl: ' + material_node)
    clone = c.duplicate(material_node, inputConnections=True,
                        name='OB_CC_' + material_node.split(':')[-1] + '#')[0]
    if kind == 'VRayBlendMtl':
        base = attr(material_node, 'base_material', 'baseMaterial')
        source = c.connectionInfo(base, sourceFromDestination=True)
        if not source:
            raise RuntimeError('Blend material has no base material: ' + material_node)
        upstream, output = source.split('.', 1)
        corrected = _cc_clone(upstream, channel, nodes, visited)
        wire(corrected + '.' + output, attr(clone, 'base_material', 'baseMaterial'))
        return clone
    target = clone + '.' + CC_CHANNELS[channel]
    if c.getAttr(target, lock=True):
        raise RuntimeError('Material channel is locked: ' + target)
    correction = c.shadingNode('VRayColorCorrection', asTexture=True,
                              name='OB_' + channel + '_CC#')
    nodes.append(correction)
    if channel != 'Roughness':
        _cc_input(target, correction + '.texture_map')
        # Disconnect separate RGB inputs before connecting the compound.
        for child in c.attributeQuery(CC_CHANNELS[channel], node=clone, listChildren=True) or []:
            plug = clone + '.' + child
            incoming = c.connectionInfo(plug, sourceFromDestination=True)
            if incoming and c.isConnected(incoming, plug):
                c.disconnectAttr(incoming, plug)
        wire(correction + '.outColor', target)
    else:
        # V-Ray's reflectionGlossiness plug stores roughness when either switch applies.
        rough = c.getAttr(clone + '.useRoughness') or (
            c.objExists(clone + '.shadingModel') and c.getAttr(clone + '.shadingModel') == 1)
        incoming = c.connectionInfo(target, sourceFromDestination=True)
        value = c.getAttr(target)
        if not rough:
            inverse = c.shadingNode('reverse', asUtility=True, name='OB_glossToRough#')
            if incoming:
                wire(incoming, inverse + '.inputX')
            else:
                c.setAttr(inverse + '.inputX', value)
            incoming = inverse + '.outputX'
        for component in c.attributeQuery('texture_map', node=correction, listChildren=True):
            if incoming:
                wire(incoming, correction + '.' + component)
            else:
                c.setAttr(correction + '.' + component, value)
        output = correction + '.outColorR'
        if not rough:
            inverse = c.shadingNode('reverse', asUtility=True, name='OB_roughToGloss#')
            wire(output, inverse + '.inputX'); output = inverse + '.outputX'
        wire(output, target)
    return clone


def add_color_correction(objects, channel):
    if channel not in CC_CHANNELS:
        raise RuntimeError('Choose Color, Roughness or Emissive.')
    targets = list(dict.fromkeys(object_transform(obj) for obj in objects))
    if not targets:
        raise RuntimeError('Select meshes or V-Ray proxies in Maya first.')
    def apply():
        nodes = []
        for obj in targets:
            uid = c.ls(obj, uuid=True)[0]
            active = []
            for rig in rigs():
                if c.getAttr(rig + '.active'):
                    active.extend((rig, record) for record in json.loads(c.getAttr(rig + '.records'))
                                  if record['uuid'] == uid)
            if active:
                # Use the recorded blend even while render-mask preview is assigned.
                for rig, record in active:
                    blend = role(rig, 'blendMaterial%d' % record['index'])
                    base = attr(blend, 'base_material', 'baseMaterial')
                    source = c.connectionInfo(base, sourceFromDestination=True)
                    if not source:
                        raise RuntimeError('Blend base material is missing: ' + blend)
                    material_node, output = source.split('.', 1)
                    clone = _cc_clone(material_node, channel, nodes)
                    wire(clone + '.' + output, base)
                continue
            for binding in bindings(obj):
                clone = _cc_clone(binding['mat'], channel, nodes)
                if binding['kind'] == 'proxy':
                    wire(clone + '.' + binding['output'], binding['shape'] + '.' + binding['destination'])
                else:
                    # A fresh SG isolates the selected object, including shared-material scenes.
                    sg = c.sets(renderable=True, noSurfaceShader=True, empty=True, name='OB_ccSG#')
                    for port in ('surfaceShader', 'displacementShader', 'volumeShader'):
                        incoming = c.connectionInfo(binding['sg'] + '.' + port, sourceFromDestination=True)
                        if incoming:
                            wire(clone + '.outColor' if port == 'surfaceShader' else incoming, sg + '.' + port)
                    c.sets(obj, edit=True, forceElement=sg)
        return nodes
    return atomic('Add V-Ray Color Correction', apply)


MATCH_SETTINGS = [('exposure', 'Exposure (stops)', 0, -6, 6),
                  ('saturation', 'Saturation shift', 0, -1, 1),
                  ('roughness', 'Roughness shift', 0, -1, 1),
                  ('reflection', 'Reflection gain', 1, 0, 2),
                  ('emission', 'Emission gain', 1, 0, 2)]


def _match_replace(source, destination):
    node, name = destination.split('.', 1)
    for child in c.attributeQuery(name, node=node, listChildren=True) or []:
        plug = node + '.' + child
        if c.connectionInfo(plug, isExactDestination=True):
            incoming = c.connectionInfo(plug, sourceFromDestination=True)
            c.disconnectAttr(incoming, plug)
    wire(source, destination)


def _match_clone(node, control, visited=None):
    visited = set(visited or ())
    if node in visited or c.nodeType(node) not in ('VRayMtl', 'VRayBlendMtl'):
        raise RuntimeError('Match supports VRayMtl / VRayBlendMtl base materials: ' + node)
    visited.add(node)
    clone = c.duplicate(node, inputConnections=True, name='OB_matchMaterial#')[0]
    if c.objExists(clone + '.matchController'):
        c.deleteAttr(clone + '.matchController')
    link_role(clone, 'matchController', control)
    if c.nodeType(node) == 'VRayBlendMtl':
        base = attr(node, 'base_material', 'baseMaterial')
        source = c.connectionInfo(base, sourceFromDestination=True)
        if not source:
            raise RuntimeError('Missing blend base: ' + node)
        upstream, output = source.split('.', 1)
        corrected = _match_clone(upstream, control, visited)
        wire(corrected + '.' + output, attr(clone, 'base_material', 'baseMaterial'))
        return clone
    # One live Color Correction for this material; reuse a legacy top-level CC.
    original_color = c.connectionInfo(node + '.diffuseColor', sourceFromDestination=True)
    prior = original_color.split('.')[0] if original_color else None
    if prior and c.nodeType(prior) == 'VRayColorCorrection':
        correction = c.duplicate(prior, inputConnections=True, name='OB_matchColor#')[0]
    else:
        correction = c.shadingNode('VRayColorCorrection', asTexture=True, name='OB_matchColor#')
        _cc_input(node + '.diffuseColor', correction + '.texture_map')
    # Saturation shift is added to the existing value, preserving legacy grading.
    sat = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_matchSaturation#')
    _cc_input(correction + '.saturation', sat + '.input1')
    wire(control + '.saturation', sat + '.input2')
    sat_limit = c.shadingNode('clamp', asUtility=True, name='OB_matchSaturationClamp#')
    c.setAttr(sat_limit + '.minR', -1); c.setAttr(sat_limit + '.maxR', 1)
    wire(sat + '.output', sat_limit + '.inputR')
    wire(sat_limit + '.outputR', correction + '.saturation')
    power = c.shadingNode('multiplyDivide', asUtility=True, name='OB_matchExposure#')
    c.setAttr(power + '.operation', 3); c.setAttr(power + '.input1X', 2)
    wire(control + '.exposure', power + '.input2X')
    gain = c.shadingNode('multiplyDivide', asUtility=True, name='OB_matchColorGain#')
    wire(correction + '.outColor', gain + '.input1')
    for axis in 'XYZ': wire(power + '.outputX', gain + '.input2' + axis)
    _match_replace(gain + '.output', clone + '.diffuseColor')
    # Adjust reflection roughness in [0,1], preserving maps and glossiness mode.
    rough = c.getAttr(node + '.useRoughness') or (c.objExists(node + '.shadingModel') and c.getAttr(node + '.shadingModel') == 1)
    offset = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_matchRoughness#')
    if rough:
        _cc_input(node + '.reflectionGlossiness', offset + '.input1')
    else:
        inv = c.shadingNode('reverse', asUtility=True, name='OB_matchGlossToRough#')
        _cc_input(node + '.reflectionGlossiness', inv + '.inputX')
        wire(inv + '.outputX', offset + '.input1')
    wire(control + '.roughness', offset + '.input2')
    clamp = c.shadingNode('clamp', asUtility=True, name='OB_matchRoughClamp#')
    c.setAttr(clamp + '.maxR', 1); wire(offset + '.output', clamp + '.inputR')
    output = clamp + '.outputR'
    if not rough:
        inv = c.shadingNode('reverse', asUtility=True, name='OB_matchRoughToGloss#')
        wire(output, inv + '.inputX'); output = inv + '.outputX'
    wire(output, clone + '.reflectionGlossiness')
    reflection = c.shadingNode('multDoubleLinear', asUtility=True, name='OB_matchReflection#')
    _cc_input(node + '.reflectionColorAmount', reflection + '.input1')
    wire(control + '.reflection', reflection + '.input2')
    wire(reflection + '.output', clone + '.reflectionColorAmount')
    emission = c.shadingNode('multiplyDivide', asUtility=True, name='OB_matchEmission#')
    _cc_input(node + '.illumColor', emission + '.input1')
    for axis in 'XYZ': wire(control + '.emission', emission + '.input2' + axis)
    _match_replace(emission + '.output', clone + '.illumColor')
    return clone


def match_to_ground(objects):
    targets = list(dict.fromkeys(object_transform(obj) for obj in objects))
    if not targets:
        raise RuntimeError('Select meshes or proxies in Maya first.')
    def apply():
        controls = []
        for obj in targets:
            uid = c.ls(obj, uuid=True)[0]
            entries = []
            for rig in rigs():
                if not c.getAttr(rig + '.active'): continue
                for record in json.loads(c.getAttr(rig + '.records')):
                    if record['uuid'] != uid: continue
                    base = attr(role(rig, 'blendMaterial%d' % record['index']), 'base_material', 'baseMaterial')
                    source = c.connectionInfo(base, sourceFromDestination=True)
                    if not source: raise RuntimeError('Missing blend base: ' + base)
                    mat, output = source.split('.', 1)
                    entries.append(dict(mat=mat, output=output, plug=base))
            if not entries:
                for binding in bindings(obj):
                    entry = dict(binding)
                    entry['output'] = binding.get('output', 'outColor')
                    if binding['kind'] == 'proxy': entry['plug'] = binding['shape'] + '.' + binding['destination']
                    entries.append(entry)
            existing = []
            for entry in entries:
                mat = entry['mat']
                ctrl = role(mat, 'matchController') if c.objExists(mat + '.matchController') else None
                if ctrl and c.objExists(ctrl + '.matchVersion') and c.ls(role(ctrl, 'target'), long=True)[0] == obj:
                    existing.append(ctrl)
                else: existing.append(None)
            found = set(ctrl for ctrl in existing if ctrl)
            if len(found) > 1:
                raise RuntimeError('Conflicting match controllers on ' + obj)
            control = next(iter(found)) if found else c.createNode('network', name='OB_match#', skipSelect=True)
            if not found:
                c.addAttr(control, longName='matchVersion', dataType='string')
                c.setAttr(control + '.matchVersion', '1.0', type='string'); link_role(control, 'target', obj)
                for name, label, default, low, high in MATCH_SETTINGS:
                    c.addAttr(control, longName=name, attributeType='double', defaultValue=default, minValue=low, maxValue=high, keyable=True)
            for entry, old_control in zip(entries, existing):
                if old_control == control: continue
                clone = _match_clone(entry['mat'], control)
                if 'plug' in entry:
                    wire(clone + '.' + entry['output'], entry['plug'])
                else:
                    sg = c.sets(renderable=True, noSurfaceShader=True, empty=True, name='OB_matchSG#')
                    wire(clone + '.outColor', sg + '.surfaceShader')
                    for port in ('displacementShader', 'volumeShader'):
                        source = c.connectionInfo(entry['sg'] + '.' + port, sourceFromDestination=True)
                        if source: wire(source, sg + '.' + port)
                    c.sets(obj, edit=True, forceElement=sg)
            controls.append(control)
        return controls
    return atomic('Open Object Match', apply)


def _displacement_source(sg):
    source = c.connectionInfo(sg + '.displacementShader', sourceFromDestination=True)
    if source and c.getAttr(source, type=True) not in ('float', 'double', 'doubleLinear'):
        raise RuntimeError('Scalar height displacement required: ' + source)
    return source


def _asset_displacement_input(source, destination):
    """Assets without a displacement map start at zero; ground still displaces them."""
    previous = c.connectionInfo(destination, sourceFromDestination=True)
    if previous and previous != source:
        c.disconnectAttr(previous, destination)
    if source:
        if not c.isConnected(source, destination): wire(source, destination)
    else:
        c.setAttr(destination, 0)


def _validate_displacement_mesh(obj):
    shape = mesh(obj)
    if c.nodeType(shape) != 'mesh':
        raise RuntimeError('Ground displacement blend requires meshes; proxy displacement is not supported.')
    sets = set(c.listSets(object=shape) or []) | set(c.listConnections(shape, type='VRayDisplacement') or [])
    if any(c.nodeType(node) == 'VRayDisplacement' for node in sets):
        raise RuntimeError('Use shading-group displacement for this feature; a VRayDisplacement set is assigned to ' + obj)
    if c.objExists(shape + '.vrayDisplacementType') and c.getAttr(shape + '.vrayDisplacementType') not in (0, 1):
        raise RuntimeError('Vector displacement is not supported: ' + obj)


def _proxy_displacement_route(rig, record, enabled):
    index = record['index']
    if c.getAttr(rig + '.maskPreview'):
        shader = role(rig, 'previewMaterial')
    elif enabled:
        shader = role(rig, 'proxyDisplacementMaterial%d' % index)
    else:
        shader = role(rig, 'blendMaterial%d' % index)
    destination = (role(rig, 'proxyShape%d' % index) + '.' + record['destination']
                   if record.get('kind') == 'proxy' else role(rig, 'blendSG%d' % index) + '.surfaceShader')
    wire(shader + '.outColor', destination)


def _install_proxy_displacement(rig, record, ground_source):
    if 'VRayDisplacementMtl' not in c.allNodeTypes():
        raise RuntimeError('This V-Ray build has no VRayDisplacementMtl. Proxy displacement requires a version with this node.')
    index = record['index']
    key = 'proxyDisplacementMaterial%d' % index
    blend = role(rig, 'blendMaterial%d' % index)
    if not c.objExists(rig + '.' + key):
        # Avoid silently doubling an existing shader-level displacement.
        history = c.listHistory(blend) or []
        if any(c.nodeType(node) == 'VRayDisplacementMtl' for node in history):
            raise RuntimeError('This proxy already contains shader-level displacement. Nested displacement merging is not supported yet.')
        wrapper = c.shadingNode('VRayDisplacementMtl', asShader=True, name='OB_proxyDisplacement#')
        wire(blend + '.outColor', wrapper + '.baseMaterial')
        c.setAttr(wrapper + '.vrayDisplacementAmount', 1)
        c.setAttr(wrapper + '.vrayDisplacementShift', 0)
        gain = c.shadingNode('multDoubleLinear', asUtility=True, name='OB_proxyGroundGain#')
        wire(rig + '.groundDisplacementGain', gain + '.input2')
        shifted = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_proxyGroundShift#')
        wire(gain + '.output', shifted + '.input1')
        wire(rig + '.groundDisplacementShift', shifted + '.input2')
        mask = c.shadingNode('clamp', asUtility=True, name='OB_proxyDisplacementMask#')
        c.setAttr(mask + '.maxR', 1)
        wire(role(rig, 'displacementMask') + '.outputX', mask + '.inputR')
        mix = c.shadingNode('blendColors', asUtility=True, name='OB_proxyDisplacementBlend#')
        c.setAttr(mix + '.color2', 0, 0, 0, type='double3')
        # Whole-object SG overrides can carry an original scalar displacement.
        if record.get('kind') != 'proxy':
            original = _displacement_source(role(rig, 'originalSG%d' % index))
            _asset_displacement_input(original, mix + '.color2R')
        wire(shifted + '.output', mix + '.color1R')
        wire(mask + '.outputR', mix + '.blender')
        contact = c.shadingNode('multDoubleLinear', asUtility=True, name='OB_proxyContactHeight#')
        wire(mask + '.outputR', contact + '.input1'); wire(rig + '.contactDisplacement', contact + '.input2')
        total = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_proxyDisplacementTotal#')
        wire(mix + '.outputR', total + '.input1'); wire(contact + '.output', total + '.input2')
        wire(total + '.output', wrapper + '.displacement')
        link_role(rig, key, wrapper)
        link_role(rig, 'proxyGroundGain%d' % index, gain)
        # Do not apply SG displacement a second time while the wrapper is active.
        if record.get('kind') != 'proxy':
            sg = role(rig, 'blendSG%d' % index)
            original_plug = c.connectionInfo(sg + '.displacementShader', sourceFromDestination=True)
            if original_plug:
                switch = c.shadingNode('condition', asUtility=True, name='OB_proxySGDisplacementSwitch#')
                wire(rig + '.blendGroundDisplacement', switch + '.firstTerm'); c.setAttr(switch + '.secondTerm', 1)
                c.setAttr(switch + '.colorIfTrueR', 0); wire(original_plug, switch + '.colorIfFalseR')
                wire(switch + '.outColorR', sg + '.displacementShader')
    gain = role(rig, 'proxyGroundGain%d' % index)
    if not c.isConnected(ground_source, gain + '.input1'): wire(ground_source, gain + '.input1')
    _proxy_displacement_route(rig, record, True)


def set_displacement_blend(rig, enabled):
    def apply():
        if not c.objExists(rig + '.blendGroundDisplacement'):
            c.addAttr(rig, longName='blendGroundDisplacement', attributeType='bool', defaultValue=False)
            number(rig, 'groundDisplacementGain', 1, None, None)
            number(rig, 'groundDisplacementShift', 0, None, None)
        if not enabled:
            c.setAttr(rig + '.blendGroundDisplacement', False)
            for record in json.loads(c.getAttr(rig + '.records')):
                if c.objExists(rig + '.proxyDisplacementMaterial%d' % record['index']):
                    _proxy_displacement_route(rig, record, False)
            return
        records = json.loads(c.getAttr(rig + '.records'))
        ground_list = c.sets(role(rig, 'distanceObjects'), query=True) or []
        if len(ground_list) != 1: raise RuntimeError('Exactly one ground is required for displacement blend.')
        ground = object_transform(ground_list[0]); _validate_displacement_mesh(ground)
        ground_sg, _ = material(ground)
        ground_source = _displacement_source(ground_sg)
        if not ground_source:
            raise RuntimeError('The ground shading group has no displacement connected.')
        for record in records:
            index = record['index']
            if c.nodeType(mesh(role(rig, 'target%d' % index))) == 'VRayProxy':
                _install_proxy_displacement(rig, record, ground_source)
                continue
            _validate_displacement_mesh(role(rig, 'target%d' % index))
            original = _displacement_source(role(rig, 'originalSG%d' % index))
            sg = role(rig, 'blendSG%d' % index)
            output = _displacement_source(sg)
            if not output or c.nodeType(output.split('.')[0]) != 'displacementShader':
                raise RuntimeError('The blend displacement network was replaced: ' + sg)
            disp = output.split('.')[0]
            key = 'groundDisplacementBlend%d' % index
            if c.objExists(rig + '.' + key):
                mixer = role(rig, key)
                ground_gain = role(rig, 'groundDisplacementGainNode%d' % index)
            else:
                old = c.connectionInfo(disp + '.displacement', sourceFromDestination=True)
                if not old or c.nodeType(old.split('.')[0]) not in ('addDoubleLinear', 'addDL'):
                    raise RuntimeError('Unsupported existing displacement graph: ' + disp)
                old_sum = old.split('.')[0]
                ground_gain = c.shadingNode('multDoubleLinear', asUtility=True, name='OB_groundDispGain#')
                wire(rig + '.groundDisplacementGain', ground_gain + '.input2')
                shifted = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_groundDispShift#')
                wire(ground_gain + '.output', shifted + '.input1')
                wire(rig + '.groundDisplacementShift', shifted + '.input2')
                mixer = c.shadingNode('blendColors', asUtility=True, name='OB_displacementBlend#')
                wire(shifted + '.output', mixer + '.color1R')
                mask = c.shadingNode('clamp', asUtility=True, name='OB_displacementBlendMask#')
                c.setAttr(mask + '.maxR', 1)
                wire(role(rig, 'displacementMask') + '.outputX', mask + '.inputR')
                wire(mask + '.outputR', mixer + '.blender')
                total = c.shadingNode('addDoubleLinear', asUtility=True, name='OB_blendedContactDisp#')
                wire(mixer + '.outputR', total + '.input1')
                contact = c.connectionInfo(old_sum + '.input1', sourceFromDestination=True)
                if contact: wire(contact, total + '.input2')
                switch = c.shadingNode('condition', asUtility=True, name='OB_displacementSwitch#')
                wire(rig + '.blendGroundDisplacement', switch + '.firstTerm')
                c.setAttr(switch + '.secondTerm', 1)
                wire(total + '.output', switch + '.colorIfTrueR')
                wire(old, switch + '.colorIfFalseR')
                wire(switch + '.outColorR', disp + '.displacement')
                link_role(rig, key, mixer)
                link_role(rig, 'groundDisplacementGainNode%d' % index, ground_gain)
            wire(ground_source, ground_gain + '.input1')
            _asset_displacement_input(original, mixer + '.color2R')
        c.setAttr(rig + '.blendGroundDisplacement', True)
    return atomic('Toggle Ground Displacement Blend', apply)


from PySide6 import QtCore, QtGui, QtWidgets


def blend_icon():
    """Resolution-independent, locally drawn icon; no external asset required."""
    icon = QtGui.QIcon()
    for size in (32, 64, 128, 256):
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64.0, size / 64.0)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor('#20292e'))
        painter.drawRoundedRect(QtCore.QRectF(1, 1, 62, 62), 15, 15)
        left, right = QtGui.QPainterPath(), QtGui.QPainterPath()
        left.addEllipse(QtCore.QRectF(9, 16, 33, 33))
        right.addEllipse(QtCore.QRectF(23, 16, 33, 33))
        painter.fillPath(left, QtGui.QColor('#526a77'))
        painter.fillPath(right, QtGui.QColor('#4ac9ad'))
        painter.fillPath(left.intersected(right), QtGui.QColor('#cbf3de'))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class ElidedLabel(QtWidgets.QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(23)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        text = self.fontMetrics().elidedText(self.text(), QtCore.Qt.TextElideMode.ElideMiddle, self.width())
        painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignVCenter, text)


class NumericRow(QtWidgets.QWidget):
    def __init__(self, owner, label, plug, low=0, high=1000000, soft=10, integer=False):
        super().__init__()
        self.owner, self.plug = owner, plug
        self.low, self.high, self.soft = float(low), float(high), float(soft)
        self.slider_low = max(self.low, -abs(self.soft)) if self.low < 0 else self.low
        self.integer, self.dragging = integer, False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        name = QtWidgets.QLabel(label)
        name.setFixedWidth(104)
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setDecimals(0 if integer else 3)
        self.spin.setRange(low, high)
        self.spin.setSingleStep(1 if integer else .1)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(88)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setMinimumWidth(80)
        self.slider.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(name)
        layout.addWidget(self.spin)
        layout.addWidget(self.slider, 1)
        self.spin.editingFinished.connect(self.commit_spin)
        self.slider.sliderPressed.connect(self.begin_drag)
        self.slider.sliderReleased.connect(self.end_drag)
        self.slider.valueChanged.connect(self.commit_slider)
        self.refresh(force=True)

    def refresh(self, force=False):
        if not force and (self.spin.hasFocus() or self.dragging):
            return
        value = float(c.getAttr(self.plug))
        self.soft = min(self.high, max(self.soft, value * 1.25, self.slider_low + .001))
        self.slider_low = max(self.low, min(self.slider_low, value * 1.25 if value < 0 else value))
        for widget in (self.spin, self.slider):
            widget.blockSignals(True)
        self.spin.setValue(value)
        position = round(1000 * (value - self.slider_low) / max(.000001, self.soft - self.slider_low))
        self.slider.setValue(max(0, min(1000, position)))
        for widget in (self.spin, self.slider):
            widget.blockSignals(False)
        self.setEnabled(not c.getAttr(self.plug, lock=True))

    def write(self, value):
        try:
            if self.integer:
                value = int(round(value))
            c.setAttr(self.plug, value)
            self.owner.message('Settings updated.')
        except Exception as exc:
            self.end_drag()
            self.owner.error(exc)

    def commit_spin(self):
        if abs(float(c.getAttr(self.plug)) - self.spin.value()) > 1e-7:
            self.write(self.spin.value())
        self.refresh(force=True)

    def commit_slider(self, position):
        value = self.slider_low + position / 1000.0 * (self.soft - self.slider_low)
        if self.integer:
            value = round(value)
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        self.write(value)

    def begin_drag(self):
        if not self.dragging:
            c.undoInfo(openChunk=True, chunkName='Adjust Object Blend')
            self.dragging = True

    def end_drag(self):
        if self.dragging:
            c.undoInfo(closeChunk=True)
            self.dragging = False


class MatchRow(NumericRow):
    def __init__(self, owner, controls, setting):
        self.controls = controls
        self.setting = setting[0]
        name, label, default, low, high = setting
        super().__init__(owner, label, controls[0] + '.' + name, low, high, high)
        self.setToolTip('Changes apply to every object loaded in this panel. Initial value is from the first object.')

    def write(self, value):
        try:
            def apply():
                for control in self.controls:
                    c.setAttr(control + '.' + self.setting, value)
            atomic('Adjust Object Match', apply)
            self.owner.message('Applied to %d object(s).' % len(self.controls))
        except Exception as exc:
            self.end_drag(); self.owner.error(exc)


class MatchDialog(QtWidgets.QDialog):
    def __init__(self, owner, controls):
        super().__init__(owner)
        self.setWindowTitle('Object Match - base material')
        self.setWindowIcon(blend_icon())
        self.setWindowFlags(QtCore.Qt.WindowType.Window)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(470, 410); self.resize(540, 440)
        self.controls, self.numeric = controls, []
        self.setStyleSheet(owner.styleSheet())
        layout = QtWidgets.QVBoxLayout(self)
        targets = [role(ctrl, 'target') for ctrl in controls]
        names = ElidedLabel(', '.join(targets)); names.setToolTip('\n'.join(targets))
        layout.addWidget(names)
        hint = QtWidgets.QLabel('Edits apply to all %d loaded object(s). Values initially show the first object.\nAdjust in V-Ray IPR; the blended ground coat stays unchanged.' % len(controls))
        hint.setWordWrap(True); layout.addWidget(hint)
        for setting in MATCH_SETTINGS[:4]:
            row = MatchRow(self, controls, setting); self.numeric.append(row); layout.addWidget(row)
        advanced = QtWidgets.QGroupBox('Advanced'); advanced.setCheckable(True); advanced.setChecked(False)
        sub = QtWidgets.QVBoxLayout(advanced)
        row = MatchRow(self, controls, MATCH_SETTINGS[4]); self.numeric.append(row); sub.addWidget(row)
        row.setVisible(False); advanced.toggled.connect(row.setVisible); layout.addWidget(advanced)
        help_text = QtWidgets.QLabel('Too bright: lower Exposure. Too shiny: increase Roughness first.\nUse Reflection gain for additional highlight control.')
        help_text.setWordWrap(True); layout.addWidget(help_text)
        reset = QtWidgets.QPushButton('Reset match adjustments')
        reset.clicked.connect(self.reset); layout.addWidget(reset)
        self.status = QtWidgets.QLabel('Existing textures and material settings are the starting point.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.timer = QtCore.QTimer(self); self.timer.setInterval(450)
        self.timer.timeout.connect(self.refresh); self.timer.start()

    def message(self, text):
        self.status.setText(text)

    def error(self, exc):
        self.message(str(exc)); c.warning(str(exc))

    def refresh(self):
        try:
            for row in self.numeric: row.refresh()
        except RuntimeError:
            self.close()

    def reset(self):
        try:
            def apply():
                for control in self.controls:
                    for name, label, default, low, high in MATCH_SETTINGS:
                        c.setAttr(control + '.' + name, default)
            atomic('Reset Object Match', apply)
            for row in self.numeric: row.refresh(force=True)
            self.message('Match adjustments reset; prior material settings preserved.')
        except Exception as exc: self.error(exc)

    def closeEvent(self, event):
        self.timer.stop()
        for row in self.numeric: row.end_drag()
        super().closeEvent(event)


class UI(QtWidgets.QDialog):
    def __init__(self, parent=None):
        if parent is None:
            try:
                import maya.OpenMayaUI as omui
                from shiboken6 import wrapInstance
                pointer = omui.MQtUtil.mainWindow()
                parent = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
            except (RuntimeError, ImportError):
                parent = None
        super().__init__(parent)
        self.setObjectName('ObjectBlendWindow')
        self.setWindowTitle('Object Blend 2.1.1')
        self.setWindowIcon(blend_icon())
        self.setWindowFlags(QtCore.Qt.WindowType.Window)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(470, 640)
        self.resize(560, 900)
        self.collection = self.ground = self.rig = None
        self.rows, self.numeric, self.checks = [], [], []
        self.expanded = {}
        self.busy = False
        # Keep Maya's native palette, controls and selection highlight.
        # Only spacing and typography are local to this dialog.
        self.setStyleSheet('''
            QLabel#Title { font-size: 16px; font-weight: bold; }
            QLabel#Section { font-weight: bold; }
            QLabel#Version { padding: 4px; }
            QPushButton { min-height: 26px; padding: 2px 8px; }
            QLineEdit, QDoubleSpinBox, QComboBox { min-height: 24px; }
            QTreeWidget::item { min-height: 26px; }
            QCheckBox { spacing: 8px; min-height: 24px; }
            QToolButton#Disclosure { border: none; text-align: left; padding: 3px 0; }
        ''')
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)
        header = QtWidgets.QHBoxLayout()
        symbol = QtWidgets.QLabel()
        symbol.setPixmap(blend_icon().pixmap(40, 40))
        header.addWidget(symbol)
        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(2)
        title = QtWidgets.QLabel('Object Blend'); title.setObjectName('Title')
        subtitle = QtWidgets.QLabel('Surface blending · per-object controls'); subtitle.setObjectName('Muted')
        title_box.addWidget(title); title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        version = QtWidgets.QLabel('2.1.1'); version.setObjectName('Version')
        header.addWidget(version, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)
        source_card, source_layout = self.card()
        form = QtWidgets.QGridLayout()
        form.setColumnMinimumWidth(0, 54)
        form.setColumnStretch(1, 1)
        form.setHorizontalSpacing(10); form.setVerticalSpacing(8)
        self.saved = QtWidgets.QComboBox()
        self.saved.setMinimumWidth(0)
        self.saved.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.saved.setMinimumContentsLength(12)
        self.saved.currentIndexChanged.connect(self.safe(self.choose))
        self.reload = QtWidgets.QPushButton('Refresh')
        self.reload.clicked.connect(self.safe(self.refresh))
        self.source = QtWidgets.QLineEdit(); self.source.setReadOnly(True)
        self.source.setPlaceholderText('Select a ground object in Maya')
        self.pick = QtWidgets.QPushButton('Use selected')
        self.pick.clicked.connect(self.safe(self.set_ground))
        form.addWidget(QtWidgets.QLabel('Setup'), 0, 0); form.addWidget(self.saved, 0, 1); form.addWidget(self.reload, 0, 2)
        form.addWidget(QtWidgets.QLabel('Ground'), 1, 0); form.addWidget(self.source, 1, 1); form.addWidget(self.pick, 1, 2)
        source_layout.addLayout(form)
        root.addWidget(source_card)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['GEOMETRY', 'BLEND', 'UV'])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, 120)
        self.tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(2, 65)
        self.tree.setFixedHeight(120)
        self.tree.currentItemChanged.connect(self.safe(self.select_row))
        root.addWidget(self.tree)
        buttons = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton('+  Add selection'); self.add_button.setObjectName('Primary')
        self.remove_button = QtWidgets.QPushButton('Remove / restore')
        self.add_button.clicked.connect(self.safe(self.add)); self.remove_button.clicked.connect(self.safe(self.remove))
        buttons.addWidget(self.add_button, 1); buttons.addWidget(self.remove_button)
        root.addLayout(buttons)
        self.copy_button = QtWidgets.QPushButton('Copy active Distance / Dirt settings to selected')
        self.copy_button.clicked.connect(self.safe(self.copy_settings))
        root.addWidget(self.copy_button)
        self.tree.itemSelectionChanged.connect(self.update_selection_actions)
        self.tree.setToolTip('Ctrl / Shift: select multiple rows. The active row is the copy source. Delete restores materials and removes selected rows.')
        self.delete_shortcut = QtGui.QShortcut(QtGui.QKeySequence('Delete'), self.tree)
        self.delete_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        self.delete_shortcut.activated.connect(self.safe(self.remove))
        self.cc_add = QtWidgets.QPushButton('Match to ground / Edit selected')
        self.cc_add.setToolTip('Open the reusable match controls for geometry selected in Maya. Reopening adds no new correction.')
        self.cc_add.clicked.connect(self.safe(self.add_correction))
        root.addWidget(self.cc_add)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(145)
        root.addWidget(self.scroll, 1)
        self.status = QtWidgets.QLabel('Choose a ground, then add meshes or V-Ray proxies.')
        self.status.setObjectName('Muted'); self.status.setWordWrap(True)
        self.status.setMinimumHeight(32)
        root.addWidget(self.status)
        self.refresh()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(450)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def add_correction(self, *_):
        selected = c.ls(selection=True, long=True, objectsOnly=True) or []
        controls = match_to_ground(selected)
        previous = getattr(self, 'match_dialog', None)
        if previous is not None:
            try: previous.close()
            except RuntimeError: pass
        c.select(selected, replace=True)
        self.match_dialog = MatchDialog(self, controls)
        self.match_dialog.show()
        self.message('Match controls opened for %d object(s). Reopening reuses the setup.' % len(controls))

    def card(self, title=None):
        frame = QtWidgets.QFrame(); frame.setObjectName('Card')
        frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10); layout.setSpacing(8)
        if title:
            label = QtWidgets.QLabel(title); label.setObjectName('Section'); layout.addWidget(label)
        return frame, layout

    def message(self, text):
        self.status.setText(text[:220]); self.status.setToolTip(text)

    def error(self, exc):
        traceback.print_exc()
        self.message(str(exc))
        c.warning(str(exc))

    def safe(self, function):
        def call(*args):
            try:
                return function(*args)
            except Exception as exc:
                self.error(exc)
        return call

    def refresh(self, *_):
        selected_before = set(self.selected_rigs())
        if self.collection and not c.objExists(self.collection):
            self.collection = self.ground = self.rig = None
        if self.ground and not c.objExists(self.ground):
            self.ground = None
        available = collections() + [n for n in rigs() if c.getAttr(n + '.active') and not c.objExists(n + '.collectionParent')]
        self.saved.blockSignals(True); self.saved.clear()
        self.saved.addItem('New setup', None)
        for node in available:
            self.saved.addItem(node, node)
        self.saved.setCurrentIndex(max(0, self.saved.findData(self.collection)))
        self.saved.blockSignals(False)
        if self.collection:
            self.ground = role(self.collection, 'ground')
        self.source.setText((self.ground or '').split('|')[-1])
        self.source.setToolTip(self.ground or '')
        self.pick.setEnabled(not bool(self.collection))
        self.add_button.setEnabled(bool(self.ground))
        self.rows = members(self.collection) if self.collection else []
        if self.rig not in self.rows:
            self.rig = self.rows[-1] if self.rows else None
        self.tree.blockSignals(True); self.tree.clear()
        for child in self.rows:
            target = role(child, 'target0')
            item = QtWidgets.QTreeWidgetItem([target.split('|')[-1], MODE_LABELS[c.getAttr(child + '.maskMode')]])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, child)
            item.setToolTip(0, target)
            uv, detail = uv_status(target)
            item.setText(2, uv); item.setToolTip(2, detail)
            if uv != 'UV OK':
                item.setForeground(2, QtGui.QBrush(QtGui.QColor('#d5a85c')))
                item.setIcon(2, self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning))
            self.tree.addTopLevelItem(item)
            if child == self.rig:
                self.tree.setCurrentItem(item)
        if selected_before:
            for index in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(index)
                item.setSelected(item.data(0, QtCore.Qt.ItemDataRole.UserRole) in selected_before)
        self.tree.blockSignals(False)
        self.update_selection_actions()
        self.draw()

    def choose(self, *_):
        value = self.saved.currentData()
        self.collection = edit_collection(value) if value else None
        self.rig = None
        if not value:
            self.ground = None
        self.refresh()

    def set_ground(self, *_):
        selected = c.ls(selection=True, long=True, objectsOnly=True) or []
        if len(selected) != 1:
            raise RuntimeError('Select exactly one ground mesh or proxy in Maya.')
        self.ground = object_transform(selected[0]); self.refresh()

    def add(self, *_):
        selected = c.ls(selection=True, long=True, objectsOnly=True) or []
        if not selected:
            raise RuntimeError('Select new meshes or proxies in Maya first.')
        if not self.ground:
            raise RuntimeError('Set the ground first.')
        old = set(self.rows)
        self.collection = add_objects(self.collection, selected, self.ground)
        added = [n for n in members(self.collection) if n not in old]
        if added:
            self.rig = added[-1]
        self.refresh(); self.message('%d object(s) added. Each row has independent settings.' % len(added))

    def select_row(self, current, previous=None):
        self.rig = current.data(0, QtCore.Qt.ItemDataRole.UserRole) if current else None
        self.update_selection_actions(); self.draw()

    def selected_rigs(self):
        return [item.data(0, QtCore.Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]

    def update_selection_actions(self):
        selected = self.selected_rigs()
        self.remove_button.setEnabled(bool(selected))
        self.copy_button.setEnabled(self.rig in selected and len(selected) > 1)
        source = role(self.rig, 'target0') if self.rig and c.objExists(self.rig) else 'none'
        self.copy_button.setToolTip('Source: %s. Copies mode, Distance, Dirt, strength, falloff and noise to the other selected rows. Displacement and Object Match stay unchanged.' % source)

    def copy_settings(self, *_):
        selected = self.selected_rigs()
        if self.rig not in selected or len(selected) < 2:
            raise RuntimeError('Select at least two list rows with Ctrl / Shift. The active row is the source.')
        source = role(self.rig, 'target0')
        count = copy_blend_settings(self.rig, selected)
        self.refresh()
        self.message('Copied Distance / Dirt settings from %s to %d object(s).' % (source.split('|')[-1], count))

    def remove(self, *_):
        selected = self.selected_rigs()
        if selected:
            remove_blend_targets(selected)
            self.rig = None; self.refresh()
            self.message('%d object(s) removed from list; original materials restored. Ctrl+Z to undo.' % len(selected))

    def numeric_row(self, layout, label, plug, low=0, high=1000000, soft=10, integer=False):
        row = NumericRow(self, label, plug, low, high, soft, integer)
        self.numeric.append(row); layout.addWidget(row)
        return row

    def check(self, layout, label, plug, setter=None):
        checkbox = QtWidgets.QCheckBox(label)
        checkbox.setChecked(bool(c.getAttr(plug)))
        checkbox.toggled.connect(self.safe(setter or (lambda value: c.setAttr(plug, value))))
        self.checks.append((checkbox, plug)); layout.addWidget(checkbox)
        return checkbox

    def disclosure(self, layout, title, key):
        toggle = QtWidgets.QToolButton(); toggle.setObjectName('Disclosure')
        toggle.setText(title); toggle.setCheckable(True)
        toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        body = QtWidgets.QWidget(); body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(0, 5, 0, 4); body_layout.setSpacing(8)
        def change(value):
            self.expanded[key] = value
            body.setVisible(value)
            toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow if value else QtCore.Qt.ArrowType.RightArrow)
        toggle.toggled.connect(change)
        toggle.setChecked(self.expanded.get(key, False)); change(toggle.isChecked())
        layout.addWidget(toggle); layout.addWidget(body)
        return body_layout

    def draw(self):
        for row in self.numeric:
            row.end_drag()
        self.numeric, self.checks = [], []
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        body = QtWidgets.QWidget(); body.setObjectName('ScrollBody')
        self.body_layout = QtWidgets.QVBoxLayout(body)
        self.body_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        self.body_layout.setContentsMargins(0, 0, 3, 0); self.body_layout.setSpacing(10)
        self.scroll.setWidget(body)
        if not self.rig:
            empty = QtWidgets.QLabel('Select an object row to edit its blend.\nNew objects start in Distance mode.')
            empty.setObjectName('Muted'); empty.setWordWrap(True)
            self.body_layout.addWidget(empty); self.body_layout.addStretch(); return
        rig = self.rig; dirt = role(rig, 'dirtTexture')
        card, layout = self.card()
        target = role(rig, 'target0')
        label = ElidedLabel(target.split('|')[-1]); label.setToolTip(target); layout.addWidget(label)
        uv, detail = uv_status(target)
        if uv != 'UV OK':
            warning = QtWidgets.QLabel(uv + ': ' + detail + ' Use Refresh after editing UVs.')
            warning.setWordWrap(True); layout.addWidget(warning)
        self.mode = QtWidgets.QComboBox()
        for value in (1, 0, 2):
            self.mode.addItem(MODE_LABELS[value], value)
        self.mode.currentIndexChanged.connect(self.safe(self.set_mode))
        layout.addWidget(self.mode)
        self.body_layout.addWidget(card)
        self.displacement_panel, disp_body = self.card('DISPLACEMENT · DISTANCE MASK')
        self.has_displacement = True
        enabled = c.objExists(rig + '.blendGroundDisplacement') and c.getAttr(rig + '.blendGroundDisplacement')
        self.disp_toggle = QtWidgets.QCheckBox('Blend ground displacement')
        self.disp_toggle.setChecked(bool(enabled))
        self.disp_toggle.setEnabled(self.has_displacement)
        self.disp_toggle.toggled.connect(self.toggle_displacement)
        disp_body.addWidget(self.disp_toggle)
        values = QtWidgets.QWidget()
        value_layout = QtWidgets.QVBoxLayout(values)
        value_layout.setContentsMargins(0, 0, 0, 0)
        for label, name, default, soft in [('Ground gain', 'groundDisplacementGain', 1, 2),
                                           ('Ground shift', 'groundDisplacementShift', 0, 10)]:
            plug = rig + '.' + name
            if c.objExists(plug):
                self.numeric_row(value_layout, label, plug, -1000000, 1000000, soft)
            else:
                # Show defaults before the optional displacement graph is created.
                row = QtWidgets.QWidget(); fields = QtWidgets.QHBoxLayout(row)
                fields.setContentsMargins(0, 0, 0, 0); fields.setSpacing(10)
                caption = QtWidgets.QLabel(label); caption.setFixedWidth(104)
                spin = QtWidgets.QDoubleSpinBox(); spin.setDecimals(3); spin.setValue(default)
                spin.setFixedWidth(88); spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
                slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal); slider.setMinimumWidth(80)
                slider.setRange(-1000, 1000); slider.setValue(round(default / soft * 1000))
                fields.addWidget(caption); fields.addWidget(spin); fields.addWidget(slider, 1)
                value_layout.addWidget(row)
        values.setEnabled(bool(enabled) and self.has_displacement)
        disp_body.addWidget(values)
        height = self.numeric_row(disp_body, 'Contact height', rig + '.contactDisplacement', -1000000, 1000000, 10)
        height.setEnabled(self.has_displacement)
        text = ('No asset displacement needed: starts from zero and receives the ground displacement. Ground needs a displacement map. Distance mask only.'
                if self.has_displacement else 'Displacement blend requires a mesh target; V-Ray proxy displacement is not supported.')
        note = QtWidgets.QLabel(text); note.setWordWrap(True); disp_body.addWidget(note)
        self.body_layout.addWidget(self.displacement_panel)
        self.distance_panel, distance = self.card('DISTANCE')
        self.numeric_row(distance, 'Radius', rig + '.distance', .0001, soft=20)
        self.body_layout.addWidget(self.distance_panel)
        self.dirt_panel, dirt_layout = self.card('DIRT')
        self.numeric_row(dirt_layout, 'Radius', dirt + '.radius', .0001, soft=20)
        self.numeric_row(dirt_layout, 'Falloff', dirt + '.falloff', 0, soft=5)
        self.check(dirt_layout, 'Only ground can occlude', rig + '.dirtGroundOnly', lambda value: dirt_scope(rig, value))
        advanced = self.disclosure(dirt_layout, 'Dirt details', 'dirt')
        for name, label, low, high, soft, integer in (
                ('distribution', 'Distribution', 0, 1000000, 5, False),
                ('subdivs', 'Samples', 1, 256, 32, True),
                ('biasX', 'Bias X', -1, 1, 1, False),
                ('biasY', 'Bias Y', -1, 1, 1, False),
                ('biasZ', 'Bias Z', -1, 1, 1, False)):
            self.numeric_row(advanced, label, dirt + '.' + name, low, high, soft, integer)
        for name, label in [('ignoreSelfOcclusion', 'Ignore self occlusion'), ('ignoreBump', 'Ignore bump'), ('doubleSided', 'Double sided')]:
            self.check(advanced, label, dirt + '.' + name)
        self.body_layout.addWidget(self.dirt_panel)
        common, common_layout = self.card('BLEND')
        self.numeric_row(common_layout, 'Strength', rig + '.strength', 0, 1, 1)
        self.numeric_row(common_layout, 'Falloff', rig + '.falloff', .01, 10, 5)
        noise = self.disclosure(common_layout, 'Noise', 'noise')
        self.numeric_row(noise, 'Amount', rig + '.noiseAmount', 0, 1, 1)
        self.numeric_row(noise, 'Scale', rig + '.noiseScale', .001, soft=10)
        self.numeric_row(noise, 'Frequency', rig + '.noiseFrequency', .001, soft=5)
        self.body_layout.addWidget(common)
        previews, preview_layout = self.card('PREVIEW')
        self.check(preview_layout, 'Render mask · V-Ray IPR', rig + '.maskPreview', lambda value: preview(rig, value))
        self.guides = QtWidgets.QCheckBox('Viewport radius guides')
        visible = c.objExists(rig + '.viewportGuides') and c.getAttr(role(rig, 'viewportGuides') + '.visibility')
        self.guides.setChecked(bool(visible))
        self.guides.toggled.connect(self.safe(lambda value: viewport_guides(rig, value)))
        preview_layout.addWidget(self.guides)
        help_label = QtWidgets.QLabel('Guides indicate radius at the pivot. Use V-Ray IPR for the surface mask.')
        help_label.setObjectName('Muted'); help_label.setWordWrap(True); preview_layout.addWidget(help_label)
        self.body_layout.addWidget(previews); self.body_layout.addStretch()
        self.sync_mode()
        self.body_layout.activate()
        body.adjustSize()

    def toggle_displacement(self, enabled):
        try:
            set_displacement_blend(self.rig, enabled)
            self.message('Ground displacement blend ' + ('enabled.' if enabled else 'disabled.'))
        except Exception as exc:
            self.error(exc)
        self.draw()

    def sync_mode(self):
        value = c.getAttr(self.rig + '.maskMode')
        self.mode.blockSignals(True); self.mode.setCurrentIndex(self.mode.findData(value)); self.mode.blockSignals(False)
        self.distance_panel.setVisible(value != 0)
        self.dirt_panel.setVisible(value != 1)
        self.displacement_panel.setVisible(True)
        self.displacement_panel.setEnabled(self.has_displacement)
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == self.rig:
                item.setText(1, MODE_LABELS[value])

    def set_mode(self, *_):
        c.setAttr(self.rig + '.maskMode', self.mode.currentData())
        self.sync_mode()

    def poll(self):
        if not self.isVisible() or self.busy or any(row.dragging for row in self.numeric):
            return
        self.busy = True
        try:
            if self.collection and (not c.objExists(self.collection) or members(self.collection) != self.rows):
                self.refresh(); return
            if self.rig and c.objExists(self.rig):
                enabled = c.objExists(self.rig + '.blendGroundDisplacement') and c.getAttr(self.rig + '.blendGroundDisplacement')
                if bool(enabled) != self.disp_toggle.isChecked():
                    self.draw()
                self.sync_mode()
                for row in self.numeric:
                    row.refresh()
                for checkbox, plug in self.checks:
                    checkbox.blockSignals(True); checkbox.setChecked(bool(c.getAttr(plug))); checkbox.blockSignals(False)
                visible = c.objExists(self.rig + '.viewportGuides') and c.getAttr(role(self.rig, 'viewportGuides') + '.visibility')
                self.guides.blockSignals(True); self.guides.setChecked(bool(visible)); self.guides.blockSignals(False)
        except (RuntimeError, ValueError):
            # A scene replacement can briefly invalidate saved node handles.
            self.collection = self.ground = self.rig = None
            self.refresh()
        finally:
            self.busy = False

    def closeEvent(self, event):
        self.timer.stop()
        for row in self.numeric:
            row.end_drag()
        super().closeEvent(event)


def show():
    global _ui
    previous_collection = None
    previous_rig = None
    try:
        previous = globals().get('_ui')
        if previous is None:
            previous = next((w for w in QtWidgets.QApplication.topLevelWidgets()
                             if w.objectName() == 'ObjectBlendWindow'), None)
        if previous is not None:
            previous_collection = getattr(previous, 'collection', None)
            previous_rig = getattr(previous, 'rig', None)
            if isinstance(previous, QtWidgets.QWidget):
                previous.close()
    except RuntimeError:
        pass
    if c.window(WINDOW, exists=True):
        c.deleteUI(WINDOW)
    _ui = UI()
    if previous_collection and c.objExists(previous_collection):
        _ui.collection, _ui.rig = previous_collection, previous_rig
        _ui.refresh()
    _ui.show()
    _ui.raise_()
    return _ui


def _install_payload(source, scripts_dir, icons_dir):
    """Install only this tool's files; callers may supply isolated test directories."""
    from pathlib import Path
    import os, tempfile
    compile(source, 'object_blend_runtime.py', 'exec')
    scripts = Path(scripts_dir) / 'object_blend_tool'
    icons = Path(icons_dir)
    scripts.mkdir(parents=True, exist_ok=True); icons.mkdir(parents=True, exist_ok=True)
    runtime = scripts / 'object_blend_runtime.py'
    def write_atomic(path, data):
        fd, temporary = tempfile.mkstemp(prefix=path.stem + '_', suffix='.tmp', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'wb') as stream: stream.write(data)
            os.replace(temporary, str(path))
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    if runtime.exists(): write_atomic(runtime.with_suffix('.py.bak'), runtime.read_bytes())
    write_atomic(runtime, source.encode('utf-8'))
    icon = icons / 'object_blend_tool.png'
    buffer = QtCore.QBuffer(); buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    if not blend_icon().pixmap(64, 64).save(buffer, 'PNG'):
        raise RuntimeError('Could not create the shelf icon.')
    write_atomic(icon, bytes(buffer.data()))
    return str(runtime), str(icon)


def _shelf_command(runtime):
    # Read source on each click: no stale imported module / bytecode after an update.
    return ("from pathlib import Path\nimport types, sys\n"
            "_ob_path = %r\n"
            "_ob_old = sys.modules.get('_object_blend_runtime')\n"
            "_ob_mod = types.ModuleType('_object_blend_runtime')\n"
            "_ob_mod.__file__ = _ob_path\n"
            "_ob_mod._ui = getattr(_ob_old, '_ui', None)\n"
            "exec(compile(Path(_ob_path).read_text(encoding='utf-8'), _ob_path, 'exec'), _ob_mod.__dict__)\n"
            "sys.modules['_object_blend_runtime'] = _ob_mod\n"
            "_ob_mod.show()\n") % runtime


def _install_shelf(runtime, icon, shelf_top, shelf_dir, cmds=None):
    import os
    cmds = cmds or c
    shelves = cmds.shelfTabLayout(shelf_top, query=True, childArray=True) or []
    shelf = next((name for name in shelves if name.split('|')[-1] == 'ObjectBlend'), None)
    if shelf is None: shelf = cmds.shelfLayout('ObjectBlend', parent=shelf_top)
    buttons = []
    for child in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.objectTypeUI(child) == 'shelfButton' and cmds.shelfButton(child, query=True, docTag=True) == 'ObjectBlend.Tool':
            buttons.append(child)
    options = dict(label='Object Blend', annotation='Object Blend 2.1.1 - open tool',
                   image=icon, sourceType='python', command=_shelf_command(runtime),
                   docTag='ObjectBlend.Tool', style='iconOnly')
    if buttons:
        cmds.shelfButton(buttons[0], edit=True, **options)
        for duplicate in buttons[1:]: cmds.deleteUI(duplicate)
    else:
        cmds.shelfButton(parent=shelf, **options)
    os.makedirs(shelf_dir, exist_ok=True)
    cmds.saveShelf(shelf, os.path.join(shelf_dir, 'shelf_ObjectBlend'))
    shelves = cmds.shelfTabLayout(shelf_top, query=True, childArray=True) or []
    index = next(i for i, name in enumerate(shelves, 1) if name.split('|')[-1] == 'ObjectBlend')
    cmds.optionVar(intValue=('shelfLoad%d' % index, 0))
    for key, value in [('shelfName', 'ObjectBlend'), ('shelfFile', 'shelf_ObjectBlend'), ('shelfAlign', 'left')]:
        cmds.optionVar(stringValue=(key + str(index), value))
    cmds.shelfTabLayout(shelf_top, edit=True, selectTab=shelf)
    return shelf


def _install_locations(cmds=None):
    """Use the user's profile, never a semicolon-separated plugin search path."""
    from pathlib import Path
    cmds = cmds or c
    # userShelfDir/userBitmapsDir may be search-path lists (e.g. Prism).
    # userPrefDir identifies the actual Maya version's personal profile.
    raw = cmds.internalVar(userPrefDir=True)
    if not raw or ';' in raw:
        raise RuntimeError('Maya did not return a single user preference directory: %r' % raw)
    prefs = Path(raw)
    return str(prefs.parent / 'scripts'), str(prefs / 'icons'), str(prefs / 'shelves')


def install_tool(source=None):
    from pathlib import Path
    import maya.mel as mel
    source = source if source is not None else Path(__file__).read_text(encoding='utf-8')
    shelf_top = mel.eval('$tmpObjectBlendShelf = $gShelfTopLevel')
    if not shelf_top or not c.shelfTabLayout(shelf_top, exists=True):
        raise RuntimeError('Open Maya with the Shelf visible, then drop the installer onto a viewport.')
    scripts_dir, icons_dir, shelf_dir = _install_locations()
    Path(shelf_dir).mkdir(parents=True, exist_ok=True)
    runtime, icon = _install_payload(source, scripts_dir, icons_dir)
    if any(name.split('|')[-1] == 'ObjectBlend' for name in (c.shelfTabLayout(shelf_top, query=True, childArray=True) or [])):
        mel.eval('loadNamedShelf("ObjectBlend")')
    _install_shelf(runtime, icon, shelf_top, shelf_dir)
    c.savePrefs(general=True)
    exec(_shelf_command(runtime), {})
    c.inViewMessage(amg='Object Blend 2.1.1 installed / updated. Shelf: ObjectBlend', pos='topCenter', fade=True)
    return runtime


def onMayaDroppedPythonFile(*args):
    return install_tool()


if __name__ == '__main__':
    show()
