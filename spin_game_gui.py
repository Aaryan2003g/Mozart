# spin_game_gui.py
# Mozart Dice Spin Game — GUI version
# Requirements: pip install mido
# Windows-only "Play" button uses os.startfile to open the generated MIDI in your default player (e.g., VLC)
# Place this file next to your Mozart MIDIs (confuta.mid, jm_mozdi.mid, mozeine.mid, cosifn2t.mid, etc.)

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

# -----------------------------
# MIDI helpers
# -----------------------------
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

# -----------------------------
# Bar extraction (safe bars only)
# -----------------------------

def extract_clean_bars(mid: MidiFile) -> List[List[Tuple[int, Message]]]:
    """
    Detect bar boundaries and return bars that start and end in silence (no sustained notes crossing).
    Returned as list of bars; each bar is list of (rel_tick, msg) with delta times within the bar.
    """
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

# -----------------------------
# Melody building from spins
# -----------------------------

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

    # For each spin (3 or 4), we map the dice sum (2..12) to a 4-bar phrase
    # We create a dice table with 11 choices per spin. Each choice = 4 random bars from pool.
    phrase_len_bars = 4
    dice_table: List[List[List[Tuple[int, str, int, List[Tuple[int, Message]]]]]] = []

    for spin_idx in range(len(spins)):
        rng.shuffle(pool)
        choices_for_spin: List[List[Tuple[int, str, int, List[Tuple[int, Message]]]]] = []
        # Build 11 choices (for sums 2..12); each choice is a list of 4 bars
        pos = 0
        for _ in range(11):
            phrase = [pool[(pos + k) % len(pool)] for k in range(phrase_len_bars)]
            pos = (pos + phrase_len_bars) % len(pool)
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
        # Append the 4 bars
        for src_tpb, name, bar_idx, bar in phrase:
            # scale rel ticks to output tpb
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

# -----------------------------
# GUI
# -----------------------------

class SpinGameApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mozart Dice Spin Game")
        self.geometry("840x720")
        self.resizable(True, True)

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
            messagebox.showerror("No MIDI files", "No .mid files found next to this app. Place your Mozart MIDIs beside spin_game_gui.py and restart.")
            self.destroy()
            return

        # Top: files loaded
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=(12, 6))
        ttk.Label(top, text="Mozart files loaded:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(top, text=", ".join([name for name, _ in self.midis]), wraplength=800).pack(anchor=tk.W)

        # Controls
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=12, pady=6)

        ttk.Label(ctrl, text="Spins:").grid(row=0, column=0, sticky=tk.W)
        self.spins_var = tk.IntVar(value=4)
        ttk.Radiobutton(ctrl, text="3", variable=self.spins_var, value=3).grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(ctrl, text="4", variable=self.spins_var, value=4).grid(row=0, column=2, sticky=tk.W)

        ttk.Label(ctrl, text="Seed (optional):").grid(row=0, column=3, padx=(16, 0), sticky=tk.W)
        self.seed_var = tk.StringVar(value="")
        ttk.Entry(ctrl, textvariable=self.seed_var, width=10).grid(row=0, column=4, sticky=tk.W)

        ttk.Label(ctrl, text="Ticks/Beat:").grid(row=0, column=5, padx=(16, 0), sticky=tk.W)
        self.tpb_var = tk.IntVar(value=480)
        ttk.Entry(ctrl, textvariable=self.tpb_var, width=8).grid(row=0, column=6, sticky=tk.W)

        ttk.Button(ctrl, text="Reset", command=self.reset_game).grid(row=0, column=7, padx=8)

        # Spin area
        spinf = ttk.LabelFrame(self, text="Spin the Dice (2–12)")
        spinf.pack(fill=tk.X, padx=12, pady=6)

        self.forced_var = tk.StringVar(value="")
        ttk.Label(spinf, text="Force result:").grid(row=0, column=0, padx=(8, 4), pady=8)
        ttk.Entry(spinf, textvariable=self.forced_var, width=6).grid(row=0, column=1, padx=(0, 12))
        ttk.Button(spinf, text="Spin!", command=self.spin_once).grid(row=0, column=2, padx=6)
        ttk.Button(spinf, text="Undo last", command=self.undo_last).grid(row=0, column=3, padx=6)

        self.rolls_var = tk.StringVar(value="Rolls: []")
        ttk.Label(spinf, textvariable=self.rolls_var).grid(row=0, column=4, padx=12)

        # Output controls
        out = ttk.Frame(self)
        out.pack(fill=tk.X, padx=12, pady=6)
        ttk.Label(out, text="Output file:").grid(row=0, column=0, sticky=tk.W)
        self.out_var = tk.StringVar(value="mozart_spins.mid")
        ttk.Entry(out, textvariable=self.out_var, width=40).grid(row=0, column=1, padx=(4, 12))
        ttk.Button(out, text="Generate MIDI", command=self.generate).grid(row=0, column=2, padx=6)
        ttk.Button(out, text="Play", command=self.play_output).grid(row=0, column=3, padx=6)

        # Log box
        logf = ttk.LabelFrame(self, text="Game Log")
        logf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))
        self.log = tk.Text(logf, height=16, wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True)

        self.reset_game()

    def reset_game(self):
        self.current_rolls: List[int] = []
        self.rolls_var.set("Rolls: []")
        self.log.delete("1.0", tk.END)
        self._log("New game. Choose 3 or 4 spins, then hit Spin! Use 'Force result' to pick a specific 2..12.")

    def _log(self, msg: str):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def spin_once(self):
        if len(self.current_rolls) >= self.spins_var.get():
            messagebox.showinfo("All spins used", f"You chose {self.spins_var.get()} spins. Reset to play again.")
            return
        txt = (self.forced_var.get() or "").strip()
        if txt:
            try:
                total = int(txt)
            except ValueError:
                messagebox.showerror("Invalid", "Force result must be an integer 2..12")
                return
            if not (2 <= total <= 12):
                messagebox.showerror("Invalid", "Force result must be between 2 and 12")
                return
            self._log(f"Spin {len(self.current_rolls)+1}: forced → {total}")
        else:
            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            total = d1 + d2
            self._log(f"Spin {len(self.current_rolls)+1}: rolled {d1}+{d2} = {total}")
        self.current_rolls.append(total)
        self.rolls_var.set(f"Rolls: {self.current_rolls}")

    def undo_last(self):
        if not self.current_rolls:
            return
        last = self.current_rolls.pop()
        self._log(f"Undo last spin (removed {last}).")
        self.rolls_var.set(f"Rolls: {self.current_rolls}")

    def _collect_seed_tpb(self) -> Tuple[Optional[int], int]:
        # Seed
        seed_txt = (self.seed_var.get() or "").strip()
        seed = None
        if seed_txt:
            try:
                seed = int(seed_txt)
            except ValueError:
                messagebox.showwarning("Seed", "Seed must be an integer. Ignoring.")
                seed = None
        # TPB
        try:
            tpb = int(self.tpb_var.get())
        except Exception:
            tpb = 480
        return seed, tpb

    def generate(self):
        spins_needed = self.spins_var.get()
        if len(self.current_rolls) != spins_needed:
            messagebox.showinfo("Incomplete", f"You need {spins_needed} spins. Current: {len(self.current_rolls)}")
            return
        seed, tpb = self._collect_seed_tpb()
        try:
            mid, log_text = build_from_spins(self.midis, self.current_rolls, tpb_out=tpb, seed=seed)
        except Exception as e:
            messagebox.showerror("Error", f"Could not build melody: {e}")
            return
        out_name = (self.out_var.get() or "mozart_spins.mid").strip()
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
        out_name = (self.out_var.get() or "mozart_spins.mid").strip()
        if not out_name:
            messagebox.showwarning("Play", "Enter an output filename or generate first.")
            return
        path = Path(out_name).resolve()
        if not path.exists():
            messagebox.showwarning("Play", f"File not found: {path}\nGenerate it first.")
            return
        try:
            os.startfile(str(path))
        except Exception as e:
            messagebox.showerror("Play error", f"Couldn't open file: {e}")


if __name__ == "__main__":
    app = SpinGameApp()
    app.mainloop()
