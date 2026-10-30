Vendored so the dashboard works with no internet access (pinned versions):

| File | Source | License |
|---|---|---|
| three.module.min.js | https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js | MIT |
| OrbitControls.js | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js | MIT |
| hls.min.js | https://cdn.jsdelivr.net/npm/hls.js@1.5.13/dist/hls.min.js | Apache-2.0 |

three.js add-ons for the v11 3D view (bloom on the laser, sky), same pinned release, kept in their
`examples/jsm/` layout so their relative imports resolve:

| File | Source | License |
|---|---|---|
| jsm/postprocessing/{EffectComposer,RenderPass,UnrealBloomPass,OutputPass,ShaderPass,MaskPass,Pass}.js | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/ | MIT |
| jsm/shaders/{CopyShader,LuminosityHighPassShader,OutputShader}.js | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/shaders/ | MIT |
| jsm/objects/Sky.js | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/objects/Sky.js | MIT |
