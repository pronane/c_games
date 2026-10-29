#!/bin/bash
# iOS PWA deploy (no Xcode needed)
echo "Deploying PWA to GitHub Pages for iOS..."
echo "1. Copy export_web/* to docs/ for GitHub Pages"
mkdir -p docs
cp -r ../export_web/* docs/
cp -r ../assets docs/ 2>/dev/null || cp -r ../assets_hd docs/assets_hd
echo "2. Enable GitHub Pages: Settings -> Pages -> Source docs/"
echo "3. iOS users: Safari -> Share -> Add to Home Screen"
echo "Done - PWA works offline with service worker"
