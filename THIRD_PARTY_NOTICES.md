# Third-party components

The MIT license in this project covers only this project's original source. No external engine executables or model weights are bundled in this source archive. Install them from their official distributions, retaining their notices and licenses.

| Component | Official source | Licensing notes |
| --- | --- | --- |
| PySide6 / Qt for Python | https://doc.qt.io/qtforpython-6/licenses.html | LGPLv3/GPLv3/commercial options; review the modules and distribution obligations. This app uses dynamically loaded Qt libraries. |
| Pillow | https://github.com/python-pillow/Pillow | HPND / project license and bundled dependency notices |
| OpenCV | https://github.com/opencv/opencv | Apache-2.0 for current OpenCV; wheels include third-party notices |
| NumPy | https://github.com/numpy/numpy | BSD-3-Clause and bundled library notices |
| psutil | https://github.com/giampaolo/psutil | BSD-3-Clause |
| Real-ESRGAN NCNN Vulkan | https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan | MIT; retain engine/dependency notices and check separate weight terms |
| Real-ESRGAN models | https://github.com/xinntao/Real-ESRGAN | Review the model's applicable license and notices |
| Video2X | https://github.com/k4yt3x/video2x | AGPL-3.0; retain its license and corresponding-source obligations when redistributing; subprocess execution does not grant relicensing rights |
| FFmpeg / FFprobe | https://ffmpeg.org/legal.html | LGPL/GPL depends on build and enabled components, including codecs |
| RIFE | https://github.com/nihui/rife-ncnn-vulkan | MIT implementation; check the model's terms as supplied by Video2X |
| PyInstaller | https://pyinstaller.org/en/stable/license.html | GPL with bootloader distribution exception |

Before shipping a binary, audit the exact wheels, engine builds, codecs and model weights actually distributed. Preserve their license files and source/relinking provisions as applicable. The supplied PyInstaller spec keeps third-party engines and weights external; it does include dynamically loaded Python dependencies, whose notices remain relevant. Qt license materials are included in the packaged `licenses/` folder by the specification.
