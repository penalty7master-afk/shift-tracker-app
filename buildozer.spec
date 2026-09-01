[app]
title = Мой Календарь Смен
package.name = shifttracker
package.domain = org.shifttracker
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.1,cython==3.0.11,https://github.com/kivy/pyjnius/archive/master.zip
orientation = portrait
fullscreen = 0

android.permissions =
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
