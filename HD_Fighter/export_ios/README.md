# iOS Export - Two Options

## Option A: PWA (Recommended, instant, no Xcode)
The web build (export_web) already works on iOS as PWA:
1. Deploy export_web to GitHub Pages / itch.io / Netlify
2. On iPhone, open in Safari → Share → Add to Home Screen
3. Launches fullscreen, touch controls work, 60fps
4. Game already handles touch via on-screen buttons in index.html

## Option B: Native via Kivy-iOS (for App Store)
1. Install kivy-ios: pip install kivy-ios
2. Convert pygame → kivy wrapper (pygame already works on iOS via pygame-ce)
3. Create Xcode project:
   toolchain create hdfight2 ios
   toolchain build python3 pygame
   toolchain create hdfight2 --copy
4. Open in Xcode, set bundle ID com.hdfighter.game, build to device

Alternatively, use `briefcase`:
   pip install briefcase
   briefcase new  (choose iOS)
   briefcase build ios

See export_ios/build.sh
