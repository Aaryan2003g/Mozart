Here you go — a clean, final **README.md** you can drop into your repo:

```md
# Mozart Dice Game (VR Music Project)

A small game that generates new melodies by **rolling dice** and stitching **bars** from your local **MIDI** files (Mozart and friends). Includes:
- A **visual GUI** with animated dice
- A **CHAOS mode** (each bar from any file, pure randomness)
- A simpler GUI
- A console version

> Works with **.mid** files (not MP3/WAV). Place your MIDI files in the **same folder** as the app.

---

## ✨ Features
- **Dice gameplay**: choose **3 or 4 spins**; each spin contributes musical material.
- **Animated dice** (Tkinter Canvas), **force result** (type 2–12), **undo**, spins-left counter.
- **Bar-clean splicing**: prefers bars that start/end in silence to avoid stuck notes.
- **Chaos mode**: each bar can come from **any** MIDI file → wild, surprising results.
- **One-click Play** on Windows (opens in your default MIDI player, e.g., VLC).
- **Auto-detects** all `*.mid` next to the script — **no filenames to type**.

---

## 🗂 Project Structure

```

.
├─ main.py                       # Console app (dice/medley modes)
├─ spin\_game\_gui.py              # Simple GUI (buttons, no animation)
├─ mozart\_dice\_game\_gui.py       # GUI with animated dice (recommended)
├─ mozart\_dice\_game\_gui\_chaos.py # GUI with animated dice + CHAOS mode (per-bar random)
├─ \*.mid                         # Your MIDI files (e.g., confuta.mid, jm\_mozdi.mid, mozeine.mid, cosifn2t.mid)
└─ README.md

````

---

## 🔧 Requirements
- **Python 3.11+**
- **Tkinter** (bundled on Windows; on Linux/macOS install the `tk`/`python3-tk` package if needed)
- **mido** library:
  ```bash
  pip install mido
````

---

## 🚀 Quick Start (GUI)

1. Put your `.mid` files in the same folder as the scripts.
2. Install dependencies:

   ```bash
   pip install mido
   ```
3. Run a GUI:

   ```bash
   # Animated dice, structured phrases:
   python mozart_dice_game_gui.py

   # Animated dice, pure randomness (each bar from anywhere):
   python mozart_dice_game_gui_chaos.py

   # Simple GUI (no animation):
   python spin_game_gui.py
   ```

### Gameplay

* Choose **Spins** (3 or 4).
* Click **Roll!** to animate the dice.
  (Optional) Enter a value in **Force (2–12)** and click **Roll!** to pick a specific total.
* Click **Compose** → the app builds a new `.mid` file.
* Click **Play** (Windows) to open it in your default player (e.g., VLC).

---

## 🖥 Console Version

```bash
# Interactive dice:
python main.py

# Auto-roll, reproducible, custom output:
python main.py --mode dice --auto --seed 42 --out mozart_dice.mid

# Medley of whole pieces (no dice):
python main.py --mode medley --out mozart_medley.mid
```

---

## 🎼 Adding Music

* Drop **any number of `.mid` files** next to the script — **no code changes needed**.
* Best results when files share the **same time signature** (e.g., all 4/4 or all 3/4) and are **quantized** (notes end near bar lines).
* You can add Mozart, Haydn dances/minuets, Clementi sonatinas, Bach inventions, folk tunes, etc.

> The game selects **bars (measures)**, not individual beats. Bars are pulled from **all** files in the folder.

---

## 🧪 Tips for Better Output

* Curate **10–30** clean MIDIs in the same meter → more variety without chaos.
* If joins sound messy, remove MIDIs with lots of **notes crossing barlines**.
* Want maximum surprise? Use **CHAOS** mode (`mozart_dice_game_gui_chaos.py`).

---

## 📦 Build a Windows `.exe` (optional)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install mido pyinstaller

# Example: build the animated GUI (no console window)
pyinstaller --onefile --noconsole --name MozartDice mozart_dice_game_gui.py
# Output: dist\MozartDice.exe
```

* Put your `.mid` files next to the `.exe` and run it.
* To **bundle** MIDIs inside the exe, add for each file:

  ```
  --add-data "confuta.mid;."
  ```

---

## 🧰 Troubleshooting

* **“No .mid files found”** → Ensure MIDIs are in the **same folder** (not a subfolder).
* **No sound / can’t open** → Install a MIDI player (e.g., VLC) or load the `.mid` into a DAW.
* **Empty/short output** → Your MIDIs may not yield many “clean bars”. Add simpler/quantized pieces or use **CHAOS** mode.
* **Mixed meters** → Keep runs to one meter: all 4/4 or all 3/4.

---

## 📁 Large Files (Optional: Git LFS)

If you plan to commit many/large MIDIs:

```bash
git lfs install
git lfs track "*.mid"
git add .gitattributes
git commit -m "Track MIDIs with Git LFS"
```

---

## 🔌 VR Integration (Roadmap)

* Unity/Unreal hooks to trigger rolls in-scene and play back generated audio.
* Optional: key normalization / auto-transpose, dice SFX, richer animations.

---

## 📜 License

Choose a license (e.g., MIT):

```
MIT License – © Your Name
```

```

Want me to tailor this to only the scripts you plan to keep (e.g., just the chaos GUI + console), or add screenshots later?
::contentReference[oaicite:0]{index=0}
```
