#!/bin/sh
# Fetch the models tools/quality_report.py uses (all from GitHub, ~2 MB): YuNet face detector (ShiqiYu/libfacedetection.train,
# BSD-3), Haar frontal + profile cascades (opencv/opencv 4.x, BSD/Intel licence), BRISQUE LIVE model (opencv/opencv_contrib, Apache-2).
set -e
D="$(cd "$(dirname "$0")" && pwd)/models"; mkdir -p "$D"; T=$(mktemp -d); cd "$T"
git clone -q --depth 1 --filter=blob:none --sparse https://github.com/ShiqiYu/libfacedetection.train.git lfd && (cd lfd && git sparse-checkout set onnx) && cp lfd/onnx/yunet_s_640_640.onnx "$D/"
git clone -q --depth 1 --branch 4.x --filter=blob:none --sparse https://github.com/opencv/opencv.git cv && (cd cv && git sparse-checkout set data/haarcascades) && cp cv/data/haarcascades/haarcascade_frontalface_alt2.xml cv/data/haarcascades/haarcascade_profileface.xml "$D/"
git clone -q --depth 1 --filter=blob:none --sparse https://github.com/opencv/opencv_contrib.git cc && (cd cc && git sparse-checkout set modules/quality/samples) && cp cc/modules/quality/samples/brisque_model_live.yml cc/modules/quality/samples/brisque_range_live.yml "$D/"
rm -rf "$T"; echo "quality models -> $D"
