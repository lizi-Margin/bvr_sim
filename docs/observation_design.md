# Observation Design Notes

This note summarizes the observation-space design choices that led to the current `entity` observation path.

## Background

Early BVR Sim experiments used compact and extended vector observations. These vectors encoded self state, relative aircraft state, missile warnings, and team missile state using normalized Cartesian coordinates, relative velocity, range, and angular terms.

Dense reward shaping made these observations usable, but sparse terminal rewards exposed a weakness: the agent had to discover spatial structure from an unstructured vector. This made exploration and credit assignment difficult in larger scenarios.

## Canvas And LiDAR Experiments

The `canvas` observation represented the tactical picture as an RGB top-down image, similar to a multifunction display. It was easy to inspect visually and could be used with vision models, but it was memory-heavy and did not perform well enough to justify the cost.

A LiDAR-style observation was also explored. The idea was to discretize the ego-centered angular space into azimuth/elevation bins and return ray-level features such as range, radial velocity, altitude difference, lock state, and missile warning state.

This representation preserved angular structure, but it was sparse in air-combat scenarios: one aircraft usually occupies a small number of angular bins rather than a dense visual region. Standard 2D convolution therefore had limited value because there were few local texture-like features to exploit.

## Alternatives Considered

Several model-side approaches remain useful for future work:

- Object-centric encoders: detect non-empty ray bins or visible entities, then encode them as a set with DeepSets, Set Transformer, a relation network, or a graph neural network.
- Per-ray encoders: embed each ray with a small MLP, then use 1D convolution over azimuth with circular padding or use axial attention.
- Attention with position encoding: add azimuth/elevation features, relative angular position, or rotary position encoding so the model can reason about angular relationships.
- CoordConv-style features: append `sin(az)`, `cos(az)`, `sin(el)`, and `cos(el)` directly to each ray or entity feature.

## Entity Observation

The current preferred path is `obs_type: "entity"`. Instead of treating the tactical picture as an image, BVR Sim represents aircraft, missiles, and other units as rows in a fixed-width entity table.

Each entity row uses a common feature schema so a shared encoder can process every unit consistently. Useful features include:

- normalized relative position and velocity
- normalized range
- normalized radial velocity
- normalized altitude or altitude difference
- entity type indicators such as enemy, ally, and missile
- missile-specific fields such as Mach number when available
- angular position features such as `az_sin`, `az_cos`, `el_sin`, and `el_cos`

This keeps the spatial inductive bias from the LiDAR experiments while avoiding a sparse image representation. It also fits multi-agent RL models that encode each unit independently and then aggregate entity embeddings.

## Practical Guidance

For new experiments:

1. Start with `obs_type: "entity"` when the policy architecture can consume entity-oriented observations.
2. Use `compact` or `extended` for simple MLP baselines or compatibility with older training code.
3. Use image or ray-style observations only when the model architecture is designed to exploit that structure.
4. Keep entity feature dimensions uniform across aircraft, missiles, allies, and enemies; use masks or type indicators for fields that do not apply to every unit.

