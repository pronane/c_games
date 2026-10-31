# MediaPipe canonical face model

`canonical_face_model.obj` is copied unchanged from
[google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe) at
`mediapipe/modules/face_geometry/data/canonical_face_model.obj`. It is licensed under the Apache License 2.0
(`LICENSE` in this folder), Copyright The MediaPipe Authors.

It holds 468 vertices in centimetres: x is the person's left, y is up, z is towards the viewer. Sprite Forge's
`sforge/facemesh.py` fits it to the face in the photo and uses its depth as the face relief for photo3d: the nose,
the brow and eye sockets, the lips, the chin and the cheeks turning away.
