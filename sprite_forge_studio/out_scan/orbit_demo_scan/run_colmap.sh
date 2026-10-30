#!/bin/sh
# COLMAP sparse reconstruction on CPU (run from this folder). Dense: needs CUDA (patch_match_stereo) or use OpenMVS.
colmap feature_extractor --database_path db.db --image_path images --ImageReader.single_camera 1 --ImageReader.camera_model SIMPLE_RADIAL --SiftExtraction.use_gpu 0
colmap sequential_matcher --database_path db.db --SiftMatching.use_gpu 0 --SequentialMatching.overlap 10
mkdir -p sparse && colmap mapper --database_path db.db --image_path images --output_path sparse
# with a CUDA GPU you can continue with COLMAP's own dense MVS:
# colmap image_undistorter --image_path images --input_path sparse/0 --output_path dense
# colmap patch_match_stereo --workspace_path dense && colmap stereo_fusion --workspace_path dense --output_path dense/fused.ply
# colmap poisson_mesher --input_path dense/fused.ply --output_path dense/meshed.ply
