# Py File Manager — Android port

This is an Android/Kivy port of the uploaded Windows Tkinter file manager.

## Included
- Touch-friendly grid and detailed list views
- Visible selection outline
- Folder browsing and path navigation
- Search in the current folder
- Copy/cut/paste
- Rename and delete
- Favorites and color tags
- Recent files
- ZIP browsing, internal extraction, and ZIP creation
- Dark, light, black, and white themes
- Custom accent color
- Android external-storage access settings
- Opens supported files using Android apps

## Important Android difference
The original program uses Windows APIs (`os.startfile`, Windows drive discovery, Windows keep-awake, and Tkinter). Those cannot be packaged unchanged as an Android APK. This project replaces those pieces with Android/Kivy equivalents.

## Build the APK
Build on Linux/WSL with Buildozer:

```bash
python3 -m pip install buildozer cython==0.29.37
cd PyFileManagerAndroid
buildozer -v android debug
```

The APK is created under `bin/`.

For a release APK, configure a signing key and run:

```bash
buildozer android release
```

On the first build, Buildozer downloads the Android SDK/NDK and other build dependencies, so network access is required.

## GitHub one-click build
The project also contains `.github/workflows/build-apk.yml`. Upload this folder to a GitHub repository, open **Actions → Build Android APK → Run workflow**, and GitHub will attach the finished APK as a workflow artifact.
