[app]
title = HD Fighter 2
package.name = hdfight2
package.domain = com.hdfighter.game
source.dir = .
source.include_exts = py,png,json,wav,mp3
version = 2.0
requirements = python3,pygame
orientation = landscape
fullscreen = 1
android.permissions = INTERNET, VIBRATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.entrance_icon = assets/icon.png

[buildozer]
log_level = 2
warn_on_root = 1

# Build with: buildozer android debug
# Needs: pip install buildozer; sudo apt install openjdk-17-jdk
