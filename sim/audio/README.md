# Test audio

Input recordings for the frame-level testbench (`sim/run_wav.sh`).

| File | Source | Author | Licence | Notes |
|------|--------|--------|---------|-------|
| `chuck_berry_lick.wav` | [Wikimedia Commons: Electric guitar lick in the style of Chuck Berry.wav](https://commons.wikimedia.org/wiki/File:Electric_guitar_lick_in_the_style_of_Chuck_Berry.wav) | Include.aliment | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | unmodified, 44.1 kHz 16-bit stereo, 5.6 s |
| `the_lick_e_minor.wav` | [Wikimedia Commons: The Lick on electric guitar (E minor).ogg](https://commons.wikimedia.org/wiki/File:The_Lick_on_electric_guitar_(E_minor).ogg) | Skimel | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | decoded from the original Ogg Vorbis to 44.1 kHz 16-bit stereo WAV (VLC), 3.1 s |

Audio produced from these files by the simulation (`sim/out/wav/*.wav`) is a
derivative work and is likewise licensed under CC BY-SA 4.0, attributed to the
authors above.

To add your own recording, drop a WAV file here (any rate/channels/bit depth;
`tools/wavconv.py` converts it to 48 kHz mono) and run
`./run_wav.sh <name> all`. A dry DI recording (no amp or effects) works best.
