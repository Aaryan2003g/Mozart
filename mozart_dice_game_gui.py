# mozart_dice_game_gui.py
# Visual Dice Game (Tkinter Canvas) + Mozart-based melody generation from your local MIDIs
# Requirements: Python 3.11+, Tkinter (built-in), and mido -> pip install mido
# Usage: put this file next to your Mozart .mid files (confuta.mid, jm_mozdi.mid, mozeine.mid, cosifn2t.mid, etc.)
# Run:   python mozart_dice_game_gui.py

from __future__ import annotations
import os
import random
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import List, Tuple, Dict, Optional

try:
    from mido import MidiFile, MidiTrack, Message, MetaMessage, bpm2tempo
except Exception:
    raise SystemExit("This app needs the 'mido' package. Install with: pip install mido")

# =============================
# MIDI helpers
# =============================
CHANNEL_MSGS = {"note_on", "note_off", "control_change", "program_change", "pitchwheel", "aftertouch", "polytouch"}

def is_channel_msg(msg) -> bool:
    return (not getattr(msg, "is_meta", False)) and (msg.type in CHANNEL_MSGS)

def iter_abs_messages(mid: MidiFile) -> List[Tuple[int, Message]]:
    events: List[Tuple[int, Message]] = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if is_channel_msg(msg):
                events.append((t, msg.copy()))
    events.sort(key=lambda x: x[0])
    return events

def first_meta(mid: MidiFile, meta_type: str):
    for tr in mid.tracks:
        for msg in tr:
            if getattr(msg, "is_meta", False) and msg.type == meta_type:
                return msg
    return None

def get_time_signature(mid: MidiFile) -> Tuple[int, int]:
    ts = first_meta(mid, "time_signature")
    if ts:
        return ts.numerator, ts.denominator
    return 4, 4

def get_tempo(mid: MidiFile) -> int:
    st = first_meta(mid, "set_tempo")
    if st:
        return st.tempo
    return bpm2tempo(120)

def ticks_per_bar(tpb: int, numerator: int, denominator: int) -> int:
    bar_beats = numerator * (4.0 / float(denominator))
    return max(1, int(round(tpb * bar_beats)))

def to_delta_track(abs_events: List[Tuple[int, Message]]) -> MidiTrack:
    track = MidiTrack()
    if not abs_events:
        return track
    last = 0
    for t, msg in abs_events:
        dt = int(max(0, t - last))
        msg.time = dt
        track.append(msg)
        last = t
    return track

def scale_events(abs_events: List[Tuple[int, Message]], scale: float) -> List[Tuple[int, Message]]:
    return [(int(round(t * scale)), m) for t, m in abs_events]

# =============================
# Bar extraction (safe bars only)
# =============================

def extract_clean_bars(mid: MidiFile) -> List[List[Tuple[int, Message]]]:
    """Detect bar boundaries and return bars that start and end in silence."""
    tpb = mid.ticks_per_beat
    num, den = get_time_signature(mid)
    bar_len = ticks_per_bar(tpb, num, den)

    events = iter_abs_messages(mid)
    if not events:
        return []

    end_time = events[-1][0]
    n_bars = max(1, (end_time // bar_len) + 1)

    safe_bars: List[List[Tuple[int, Message]]] = []
    active: Dict[Tuple[int, int], int] = {}

    idx = 0
    for b in range(n_bars):
        start = b * bar_len
        end = (b + 1) * bar_len

        while idx < len(events) and events[idx][0] < start:
            _, m = events[idx]
            if m.type == "note_on" and m.velocity > 0:
                active[(m.channel, m.note)] = m.velocity
            elif (m.type == "note_off") or (m.type == "note_on" and m.velocity == 0):
                active.pop((m.channel, m.note), None)
            idx += 1

        starts_silent = (len(active) == 0)

        bar_events_abs: List[Tuple[int, Message]] = []
        scan_j = idx
        while scan_j < len(events) and events[scan_j][0] < end:
            t, m = events[scan_j]
            if m.type == "note_on" and m.velocity > 0:
                active[(m.channel, m.note)] = m.velocity
            elif (m.type == "note_off") or (m.type == "note_on" and m.velocity == 0):
                active.pop((m.channel, m.note), None)
            rel_t = t - start
            nm = m.copy()
            nm.time = 0
            bar_events_abs.append((rel_t, nm))
            scan_j += 1

        ends_silent = (len(active) == 0)

        if starts_silent and ends_silent and bar_events_abs:
            bar_events_abs.sort(key=lambda x: x[0])
            rel_track = []
            last = 0
            for rt, m in bar_events_abs:
                dt = int(max(0, rt - last))
                m.time = dt
                rel_track.append((rt, m))
                last = rt
            safe_bars.append(rel_track)

        idx = scan_j

    return [[(rt, m.copy()) for (rt, m) in bar] for bar in safe_bars]

# =============================
# Melody building from spins
# =============================

def build_from_spins(midis: List[Tuple[str, MidiFile]], spins: List[int], tpb_out: int, seed: Optional[int]) -> Tuple[MidiFile, str]:
    rng = random.Random(seed)

    # Pool of clean bars across all files
    pool: List[Tuple[int, str, int, List[Tuple[int, Message]]]] = []  # (src_tpb, source_name, bar_index, bar_events)
    base_tempo = None
    base_ts = None

    for name, mid in midis:
        bars_list = extract_clean_bars(mid)
        if not bars_list:
            continue
        if base_tempo is None:
            base_tempo = get_tempo(mid)
        if base_ts is None:
            base_ts = get_time_signature(mid)
        for i, b in enumerate(bars_list):
            pool.append((mid.ticks_per_beat, name, i, b))

    if not pool:
        raise RuntimeError("No clean bars found in the provided MIDIs.")

    tempo = base_tempo if base_tempo is not None else bpm2tempo(120)
    num, den = base_ts if base_ts is not None else (4, 4)

    phrase_len_bars = 4  # each spin → a 4-bar phrase
    dice_table: List[List[List[Tuple[int, str, int, List[Tuple[int, Message]]]]]] = []

    for spin_idx in range(len(spins)):
        # Shuffle pool and partition into 11 choices × 4 bars
        shuffled = pool[:]
        rng.shuffle(shuffled)
        choices_for_spin: List[List[Tuple[int, str, int, List[Tuple[int, Message]]]]] = []
        pos = 0
        for _ in range(11):  # sums 2..12
            phrase = [shuffled[(pos + k) % len(shuffled)] for k in range(phrase_len_bars)]
            pos = (pos + phrase_len_bars) % len(shuffled)
            choices_for_spin.append(phrase)
        dice_table.append(choices_for_spin)

    # Assemble events
    events: List[Tuple[int, Message]] = []
    abs_out_time = 0
    bar_len_out = ticks_per_bar(tpb_out, num, den)
    log_lines = []

    for spin_idx, total in enumerate(spins):
        total = max(2, min(12, int(total)))
        phrase = dice_table[spin_idx][total - 2]
        log_lines.append(f"Spin {spin_idx+1}: total={total} → phrase from {[name for (_, name, _, _) in phrase]}")
        for src_tpb, name, bar_idx, bar in phrase:
            scale = tpb_out / float(src_tpb)
            rel_abs = [(int(round(rt * scale)), m.copy()) for (rt, m) in bar]
            rebased = [(abs_out_time + t, m) for (t, m) in rel_abs]
            events.extend(rebased)
            abs_out_time += bar_len_out

    # Build MIDI
    events.sort(key=lambda x: x[0])
    out = MidiFile(ticks_per_beat=tpb_out)
    track = MidiTrack()
    out.tracks.append(track)
    track.append(MetaMessage("time_signature", numerator=num, denominator=den, time=0))
    track.append(MetaMessage("set_tempo", tempo=tempo, time=0))

    for m in to_delta_track(events):
        track.append(m)

    return out, "\n".join(log_lines)

# =============================
# GUI with animated dice (no external assets)
# =============================
class DiceCanvas(tk.Canvas):
    def __init__(self, master, size=120, gap=20, **kw):
        w = size * 2 + gap
        h = size
        super().__init__(master, width=w, height=h, bg="#222", highlightthickness=0, **kw)
        self.size = size
        self.gap = gap
        self.left_face = 1
        self.right_face = 1
        self._draw_static()
        self.draw_faces(1, 1)

    def _draw_static(self):
        s = self.size
        g = self.gap
        r = 24  # corner radius
        # Rounded rectangles for dice bodies
        self.create_rectangle(10, 10, 10 + s, 10 + s, fill="#fafafa", width=0, tags=("dieL",))
        self.create_rectangle(10 + s + g, 10, 10 + s + g + s, 10 + s, fill="#fafafa", width=0, tags=("dieR",))

    def draw_faces(self, left: int, right: int):
        self.left_face, self.right_face = left, right
        # Clear previous pips
        self.delete("pip")
        # Draw pips for each die
        self._draw_pips(10, 10, self.size, left)
        self._draw_pips(10 + self.size + self.gap, 10, self.size, right)

    def _draw_pips(self, x, y, s, n):
        # Pip positions (3x3 grid)
        cx = [x + s*0.2, x + s*0.5, x + s*0.8]
        cy = [y + s*0.2, y + s*0.5, y + s*0.8]
        spots = {
            1: [(1,1)],
            2: [(0,0),(2,2)],
            3: [(0,0),(1,1),(2,2)],
            4: [(0,0),(2,0),(0,2),(2,2)],
            5: [(0,0),(2,0),(1,1),(0,2),(2,2)],
            6: [(0,0),(2,0),(0,1),(2,1),(0,2),(2,2)],
        }
        r = max(4, int(s*0.06))
        for (ix, iy) in spots.get(n, []):
            self.create_oval(cx[ix]-r, cy[iy]-r, cx[ix]+r, cy[iy]+r, fill="#111", width=0, tags=("pip",))

class MozartDiceGame(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mozart Dice Game — Visual")
        self.geometry("920x720")
        self.resizable(True, True)

        # Load MIDI files from this folder
        here = Path(__file__).parent
        preferred = ["confuta.mid", "jm_mozdi.mid", "mozeine.mid", "cosifn2t.mid"]
        paths = []
        for name in preferred:
            p = here / name
            if p.exists() and p.suffix.lower() == ".mid":
                paths.append(p)
        seen = {p.resolve() for p in paths}
        for p in here.glob("*.mid"):
            if p.resolve() not in seen:
                paths.append(p)

        self.midis: List[Tuple[str, MidiFile]] = []
        for p in paths:
            try:
                self.midis.append((p.name, MidiFile(str(p))))
            except Exception as e:
                print(f"[warn] Could not read {p.name}: {e}")

        if not self.midis:
            messagebox.showerror("No MIDI files", "No .mid files found next to this app. Place your Mozart MIDIs beside the game and restart.")
            self.destroy()
            return

        # Header: files loaded
        head = ttk.Frame(self)
        head.pack(fill=tk.X, padx=14, pady=(14, 8))
        ttk.Label(head, text="Mozart files loaded:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(head, text=", ".join([name for name, _ in self.midis]), wraplength=880).pack(anchor=tk.W)

        # Dice canvas
        self.dice = DiceCanvas(self, size=140, gap=40)
        self.dice.pack(padx=14, pady=8)

        # Controls row
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=14, pady=8)

        ttk.Label(ctrl, text="Spins:").grid(row=0, column=0, sticky=tk.W)
        self.spins_var = tk.IntVar(value=4)
        ttk.Radiobutton(ctrl, text="3", variable=self.spins_var, value=3).grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(ctrl, text="4", variable=self.spins_var, value=4).grid(row=0, column=2, sticky=tk.W)

        ttk.Label(ctrl, text="Seed:").grid(row=0, column=3, padx=(16, 0), sticky=tk.W)
        self.seed_var = tk.StringVar(value="")
        ttk.Entry(ctrl, textvariable=self.seed_var, width=10).grid(row=0, column=4, sticky=tk.W)

        ttk.Label(ctrl, text="Ticks/Beat:").grid(row=0, column=5, padx=(16,0), sticky=tk.W)
        self.tpb_var = tk.IntVar(value=480)
        ttk.Entry(ctrl, textvariable=self.tpb_var, width=8).grid(row=0, column=6, sticky=tk.W)

        ttk.Button(ctrl, text="Reset", command=self.reset_game).grid(row=0, column=7, padx=8)

        # Spin area
        spinf = ttk.LabelFrame(self, text="Spin the Dice")
        spinf.pack(fill=tk.X, padx=14, pady=8)

        ttk.Label(spinf, text="Force (2–12):").grid(row=0, column=0, padx=(8,4), pady=8)
        self.force_var = tk.StringVar(value="")
        ttk.Entry(spinf, textvariable=self.force_var, width=6).grid(row=0, column=1)
        ttk.Button(spinf, text="Roll!", command=self.roll_clicked).grid(row=0, column=2, padx=8)
        ttk.Button(spinf, text="Undo", command=self.undo_last).grid(row=0, column=3, padx=8)

        self.rolls_label = ttk.Label(spinf, text="Rolls: []    (Spins left: 4)")
        self.rolls_label.grid(row=0, column=4, padx=10)

        # Output
        out = ttk.LabelFrame(self, text="Compose & Play")
        out.pack(fill=tk.X, padx=14, pady=8)

        ttk.Label(out, text="Output file:").grid(row=0, column=0, sticky=tk.W)
        self.out_var = tk.StringVar(value="mozart_dice_visual.mid")
        ttk.Entry(out, textvariable=self.out_var, width=42).grid(row=0, column=1, padx=(6,12))
        ttk.Button(out, text="Compose", command=self.compose).grid(row=0, column=2, padx=6)
        ttk.Button(out, text="Play", command=self.play_output).grid(row=0, column=3, padx=6)

        # Log
        logf = ttk.LabelFrame(self, text="Game Log")
        logf.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8,14))
        self.log = tk.Text(logf, height=14, wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True)

        # State
        self.current_rolls: List[int] = []
        self.animating = False
        self.after_id = None
        self.reset_game()

    # ---------- Dice animation ----------
    def roll_clicked(self):
        if len(self.current_rolls) >= self.spins_var.get():
            messagebox.showinfo("All spins used", f"You've selected {self.spins_var.get()} spins. Reset to play again.")
            return
        txt = (self.force_var.get() or "").strip()
        if txt:
            try:
                total = int(txt)
                if not (2 <= total <= 12):
                    raise ValueError
            except Exception:
                messagebox.showerror("Invalid", "Forced result must be an integer between 2 and 12.")
                return
            # Show directly without animation
            left = random.randint(1,6)
            right = total - left
            if right < 1 or right > 6:
                # If impossible split, just display both equal-ish
                right = max(1, min(6, total - 1))
                left = total - right
                left = max(1, min(6, left))
            self.dice.draw_faces(left, right)
            self.append_roll(total, forced=True)
        else:
            self.start_animation()

    def start_animation(self):
        if self.animating:
            return
        self.animating = True
        frames = 14
        self._animate_step(0, frames)

    def _animate_step(self, i, total_frames):
        # Random faces during spin
        lf = random.randint(1,6)
        rf = random.randint(1,6)
        self.dice.draw_faces(lf, rf)
        if i < total_frames:
            self.after_id = self.after(50, self._animate_step, i+1, total_frames)
        else:
            # Final roll
            d1 = random.randint(1,6)
            d2 = random.randint(1,6)
            self.dice.draw_faces(d1, d2)
            self.animating = False
            self.append_roll(d1 + d2, forced=False, d1=d1, d2=d2)

    def append_roll(self, total: int, forced: bool, d1: Optional[int]=None, d2: Optional[int]=None):
        self.current_rolls.append(total)
        left = self.spins_var.get() - len(self.current_rolls)
        self.rolls_label.config(text=f"Rolls: {self.current_rolls}    (Spins left: {left})")
        if forced:
            self._log(f"Spin {len(self.current_rolls)}: forced → {total}")
        else:
            self._log(f"Spin {len(self.current_rolls)}: rolled {d1}+{d2} = {total}")

    def undo_last(self):
        if not self.current_rolls:
            return
        last = self.current_rolls.pop()
        self._log(f"Undo last spin (removed {last}).")
        left = self.spins_var.get() - len(self.current_rolls)
        self.rolls_label.config(text=f"Rolls: {self.current_rolls}    (Spins left: {left})")

    def reset_game(self):
        self.current_rolls = []
        self.rolls_label.config(text=f"Rolls: []    (Spins left: {self.spins_var.get()})")
        self.log.delete("1.0", tk.END)
        self._log("New game. Choose 3 or 4 spins, then Roll! Use Force to pick a specific total (2–12).")
        self.dice.draw_faces(1, 1)

    # ---------- Compose & Play ----------
    def _collect_seed_tpb(self) -> Tuple[Optional[int], int]:
        seed_txt = (self.seed_var.get() or "").strip()
        seed = None
        if seed_txt:
            try:
                seed = int(seed_txt)
            except ValueError:
                messagebox.showwarning("Seed", "Seed must be an integer. Ignoring.")
                seed = None
        try:
            tpb = int(self.tpb_var.get())
        except Exception:
            tpb = 480
        return seed, tpb

    def compose(self):
        spins_needed = self.spins_var.get()
        if len(self.current_rolls) != spins_needed:
            messagebox.showinfo("Incomplete", f"You chose {spins_needed} spins. Current: {len(self.current_rolls)}")
            return
        seed, tpb = self._collect_seed_tpb()
        try:
            mid, log_text = build_from_spins(self.midis, self.current_rolls, tpb_out=tpb, seed=seed)
        except Exception as e:
            messagebox.showerror("Error", f"Could not build melody: {e}")
            return
        out_name = (self.out_var.get() or "mozart_dice_visual.mid").strip()
        if not out_name.lower().endswith('.mid'):
            out_name += '.mid'
        try:
            out_path = Path(out_name).resolve()
            mid.save(str(out_path))
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save MIDI: {e}")
            return
        self._log("\nSaved: " + str(out_path))
        self._log("--- Melody Details ---")
        self._log(log_text)

    def play_output(self):
        out_name = (self.out_var.get() or "mozart_dice_visual.mid").strip()
        if not out_name:
            messagebox.showwarning("Play", "Enter an output filename or compose first.")
            return
        path = Path(out_name).resolve()
        if not path.exists():
            messagebox.showwarning("Play", f"File not found: {path}\nCompose it first.")
            return
        try:
            os.startfile(str(path))
        except Exception as e:
            messagebox.showerror("Play error", f"Couldn't open file: {e}")

    # ---------- Utils ----------
    def _log(self, msg: str):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

if __name__ == "__main__":
    app = MozartDiceGame()
    app.mainloop()
