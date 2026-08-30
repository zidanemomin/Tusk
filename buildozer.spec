[app]
# (str) Title of your application
title = Py File Manager

# (str) Package name
package.name = pyfilemanager

# (str) Package domain (needed for android/ios packaging)
package.domain = com.ninjagamer

# (str) Source code where main.py live
source.dir = .

# (list) List of source files to include
source.include_exts = py,png,jpg,jpeg,kv,json,atlas,txt

# (str) Application version
version = 1.0.0

# (list) Supported Python packages
requirements = python3,kivy

orientation = portrait
fullscreen = 0

# Android
android.api = 35
android.minapi = 24
android.ndk = 28c
android.archs = arm64-v8a
android.accept_sdk_license = True
android.permissions = MANAGE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO

# (str) Icon
# icon.filename = %(source.dir)s/icon.png

[buildozer]
log_level = 2
warn_on_root = 0

# Local build cache
build_dir = .buildozer
bin_dir = bin
