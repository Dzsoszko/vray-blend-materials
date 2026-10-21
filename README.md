# V-Ray Blend Materials

Object Blend **2.1.1** blends selected objects into a ground material using Distance, Dirt, or Distance + Dirt masks. Includes a classic Maya-style UI, per-object controls, V-Ray proxy support, optional displacement blending, and reusable material matching controls.

## Requirements

- Autodesk Maya 2026 (bundled Python / PySide6).
- V-Ray for Maya. Local validation used **7.40.03**; compatibility with older builds is not guaranteed.
- Proxy displacement requires `VRayDisplacementMtl` in the installed V-Ray build.

## Install or update

1. Download [ObjectBlend_install_2_1_1.py](ObjectBlend_install_2_1_1.py) using GitHub's **Download raw file** button, or download this repository as a ZIP and extract it.
2. Keep the versioned filename and drag the local `.py` file onto a Maya viewport with the Shelf visible.
3. An **ObjectBlend** shelf tab and icon button are created, and the tool opens.

The installer writes into your personal Maya profile. Updates replace the existing installation and update the same shelf button. The previous runtime is kept as a `.py.bak` file. No additional icon download is required. Version 2.1.1 fixes installation when Prism supplies semicolon-separated shelf search paths.

Alternatively, run the full [maya_object_blend.py](maya_object_blend.py) source in Maya's Python Script Editor to open the tool without installing it.

## Usage

1. Choose **New setup**, select the ground, then **Use selected**.
2. Select meshes or V-Ray proxies in Maya and click **Add selection**.
3. Select a list row to edit its independent blend. New objects default to **Distance**.
4. Use Ctrl/Shift to select multiple list rows. **Copy active Distance / Dirt settings to selected** copies the active row's mask settings to the others.
5. **Remove / restore**, or Delete while the list has focus, restores original material assignments and removes the selected rows. Geometry stays intact. Undo is supported.

### Optional controls

- **Match to ground / Edit selected:** reusable controls for base-color exposure, saturation, reflection roughness, reflection gain, and emission. Reopening does not stack another correction. Uses Maya's geometry selection.
- **Blend ground displacement:** off by default. Blends scalar ground displacement with the object's displacement using the **Distance mask**, even in Dirt mode. Objects without displacement start at zero. Ground gain, shift, and contact height are adjustable.
- **Viewport radius guides:** pivot-centered radius references, not exact surface-falloff contours. Use V-Ray IPR to inspect the actual mask.
- **UV status:** missing or partial assignments are flagged. Proxy UVs are explicitly marked unverified. Refresh after UV edits.

## Limits

- Mesh targets require a whole-object material assignment; face-level assignments, DAG instances, and referenced assets are not supported by the blend workflow.
- Proxies require local shader-slot connections or a whole-object material override. External material-assignment files are unsupported.
- Ground displacement requires a scalar shading-group displacement source on a mesh ground. Separate `VRayDisplacement` sets and vector displacement are unsupported.
- Proxy displacement uses shader-level displacement. Already-baked proxy detail remains part of the geometry. Existing nested `VRayDisplacementMtl` networks are rejected to prevent double displacement.
- UV textures use the receiving object's UVs. Use a consistent world-space/triplanar setup for continuous ground detail.
- Ground coats are not altered by Object Match. No automatic ground-color sampling is performed.

## Validation

Maya standalone checks covered material/proxy bindings, independent masks, group copy and restore, undo/rollback, displacement values and switches, save/reload, correction reuse, and UV checks. Qt widgets were tested and rendered offscreen at several sizes. The installer was tested in isolated directories; shelf operations were tested through a simulated Maya UI API, including the Prism path regression.

**Live viewport drag-and-drop, persistence after restarting Maya, and final rendered appearance have not been independently verified.**

Detailed Hungarian instructions: [docs/README.hu.txt](docs/README.hu.txt).

The source and versioned installer contain the same code. When preparing a new release, update the version and copy the source to a new versioned installer filename to avoid Maya's dropped-module import cache.
