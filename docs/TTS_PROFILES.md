# Morrowglass TTS profiles

Morrowglass can keep the English and Vietnamese Kokoro installations separate.

## English Kokoro

Voice name format:

```text
kokoro-en:am_michael
```

Point to the Python executable from the English Kokoro environment:

```bat
set MORROWGLASS_KOKORO_EN_PYTHON=C:\MorrowglassTTS\venv\Scripts\python.exe
```

The legacy prefix `kokoro-local:` is still accepted as English Kokoro so old projects keep working.

## Vietnamese Kokoro

Voice name format:

```text
kokoro-vi:manh_dung
```

Point to the Python executable from the Vietnamese Kokoro environment:

```bat
set MORROWGLASS_KOKORO_VI_PYTHON=D:\Kokoro-Vietnamese\venv\Scripts\python.exe
```

Supported voice names currently exposed by the Vietnamese package:

```text
diem_trinh
hung_thinh
mai_linh
mai_loan
manh_dung
my_yen
ngoc_huyen
phat_tai
thanh_dat
thuc_trinh
tuan_ngoc
storyvert
duc_an
duc_duy
```

The Vietnamese bridge imports:

```python
from kokoro_vietnamese import KokoroVietnamese
```

and defaults to CPU inference. This matches the current target machine, which has Intel Iris Xe graphics and no CUDA-capable NVIDIA GPU.

## Voice controls

Both profiles expose:

- voice selection
- narration speed
- narration volume
- preview generation in the WebUI

English and Vietnamese Kokoro both use their native synthesis speed controls. Volume is applied as a lightweight FFmpeg post-process when the multiplier differs from 1.0.

The WebUI stores the selected TTS settings in `project.json`, so each video project can keep its own voice profile.

## CLI examples

English:

```bat
python morrowglass.py voice --project-dir D:\Morrowglass\Video02 --voice kokoro-en:am_michael --kokoro-en-python C:\MorrowglassTTS\venv\Scripts\python.exe --rate 0.95 --volume 1.0
```

Vietnamese:

```bat
python morrowglass.py voice --project-dir D:\Morrowglass\VideoVI01 --voice kokoro-vi:manh_dung --kokoro-vi-python D:\Kokoro-Vietnamese\venv\Scripts\python.exe --kokoro-vi-device cpu --rate 0.95 --volume 1.05
```

Environment check:

```bat
python morrowglass.py doctor --kokoro-en-python C:\MorrowglassTTS\venv\Scripts\python.exe --kokoro-vi-python D:\Kokoro-Vietnamese\venv\Scripts\python.exe
```
