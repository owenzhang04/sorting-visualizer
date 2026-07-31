"""
sort.py — Sorting algorithm visualizer

A single-file pygame application that visualizes six classic sorting
algorithms in real time. Optional race mode lets two algorithms run
side-by-side on the same input. A synchronized pseudo-code panel
highlights the line each algorithm is on, making it useful as both a
visualization and a learning tool.

Three layers:
  1. Algorithms (generators yielding operations)
  2. Runner (paces the generator against wall-clock, collects stats)
  3. Renderer (pygame event loop, draws bars, stats, pseudo-code panel)

Run:
    python sort.py
    python sort.py --race --race-left quick --race-right merge

Six algorithms ship with the app:
    bubble, selection, insertion, merge, quick, heap sort

See README.md for the full controls reference and architecture notes.
"""

from __future__ import annotations

import sys
import time
import random
import argparse
from dataclasses import dataclass, field
from typing import Iterator, Callable

import pygame


# ─────────────────────────────────────────────────────────────────────
# Operations
# ─────────────────────────────────────────────────────────────────────
#
# Algorithms yield a stream of (op, *args) tuples. The runner interprets
# them and the renderer paints state derived from them.
#
# Op vocabulary:
#   ("compare", i, j)            — highlight bars i and j yellow
#   ("swap", i, j)               — swap arr[i] and arr[j], flash red
#   ("write", i, value)          — arr[i] = value (for merge sort)
#   ("mark_sorted", i)           — bar i is in its final sorted position
#   ("line", line_index)         — highlight pseudo-code line
#
# Operations are tuples for low overhead and easy parsing.
# A function `op_kind(op)` returns the op name as a string.

OP_COMPARE = "compare"
OP_SWAP = "swap"
OP_WRITE = "write"
OP_MARK_SORTED = "mark_sorted"
OP_LINE = "line"


def op_kind(op: tuple) -> str:
    return op[0]


# ─────────────────────────────────────────────────────────────────────
# Algorithms (Phase 1: bubble sort as the architectural proof.)
# ─────────────────────────────────────────────────────────────────────


def bubble_sort(arr: list[int]) -> Iterator[tuple]:
    """Yield ops for bubble sort. Pure generator — no pygame knowledge."""
    n = len(arr)
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            yield (OP_LINE, 2)  # for j in range(...)
            yield (OP_COMPARE, j, j + 1)
            if arr[j] > arr[j + 1]:
                yield (OP_LINE, 4)  # if a[j] > a[j+1]:
                yield (OP_SWAP, j, j + 1)
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        yield (OP_LINE, 6)  # if not swapped: break
        yield (OP_MARK_SORTED, n - 1 - i)
        if not swapped:
            # Everything before i+1 is also sorted.
            for k in range(n - 2 - i, -1, -1):
                yield (OP_MARK_SORTED, k)
            break

    # Mark all as sorted (covers the break path and end-of-loop)
    for k in range(n):
        yield (OP_MARK_SORTED, k)


def selection_sort(arr: list[int]) -> Iterator[tuple]:
    """Yield ops for selection sort.

    For each i, scan ahead for the min and swap into position i.
    """
    n = len(arr)
    for i in range(n - 1):
        min_idx = i
        yield (OP_LINE, 2)  # for i in range(...)
        for j in range(i + 1, n):
            yield (OP_LINE, 3)  # for j in range(...)
            yield (OP_COMPARE, j, min_idx)
            if arr[j] < arr[min_idx]:
                yield (OP_LINE, 4)  # if a[j] < a[min_idx]:
                min_idx = j
        if min_idx != i:
            yield (OP_LINE, 5)  # swap(a, i, min_idx)
            yield (OP_SWAP, i, min_idx)
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
        yield (OP_MARK_SORTED, i)
    yield (OP_MARK_SORTED, n - 1)


def insertion_sort(arr: list[int]) -> Iterator[tuple]:
    """Yield ops for insertion sort.

    Take each element and slide it back through the sorted prefix.
    Visually striking: the sorted prefix 'grows' from the left as bars
    turn green.
    """
    n = len(arr)
    for i in range(1, n):
        yield (OP_LINE, 2)  # for i in range(1, n):
        yield (OP_LINE, 3)  # key = a[i]
        j = i
        while j > 0:
            yield (OP_LINE, 4)  # while j > 0 and ...
            yield (OP_COMPARE, j - 1, j)
            if arr[j - 1] > arr[j]:
                yield (OP_LINE, 5)  # a[j-1], a[j] = a[j], a[j-1]
                yield (OP_SWAP, j - 1, j)
                arr[j - 1], arr[j] = arr[j], arr[j - 1]
                j -= 1
            else:
                break
        yield (OP_MARK_SORTED, i)
    # Whole array is now sorted.
    for k in range(n):
        yield (OP_MARK_SORTED, k)


def merge_sort(arr: list[int]) -> Iterator[tuple]:
    """Yield ops for merge sort (top-down, recursive).

    Uses an auxiliary buffer for the merge step. We yield `write` ops
    that the renderer applies to the live array. This is how we
    visualize a normally-invisible auxiliary-buffer algorithm.
    """
    n = len(arr)
    aux = arr.copy()

    def _ms(lo: int, hi: int):
        if hi - lo <= 1:
            return
        mid = (lo + hi) // 2
        yield (OP_LINE, 3)  # mid = (lo+hi)//2
        yield from _ms(lo, mid)
        yield from _ms(mid, hi)
        yield from _merge(lo, mid, hi)

    def _merge(lo: int, mid: int, hi: int):
        yield (OP_LINE, 5)  # merge(a, lo, mid, hi)
        # Copy current slice into aux.
        for k in range(lo, hi):
            aux[k] = arr[k]
        i, j = lo, mid
        for k in range(lo, hi):
            yield (OP_LINE, 6)  # while i < mid and j < hi ...
            if i < mid and (j >= hi or aux[i] <= aux[j]):
                yield (OP_COMPARE, i, j)
                yield (OP_LINE, 7)  # a[k] = aux[i]; i++
                yield (OP_WRITE, k, aux[i])
                arr[k] = aux[i]
                i += 1
            else:
                yield (OP_COMPARE, i if i < mid else j, j if j < hi else i)
                yield (OP_LINE, 8)  # a[k] = aux[j]; j++
                yield (OP_WRITE, k, aux[j])
                arr[k] = aux[j]
                j += 1
            # After this write, the merged position k is correct.
            yield (OP_MARK_SORTED, k)

    yield from _ms(0, n)
    # Final pass to ensure everything is marked sorted.
    for k in range(n):
        yield (OP_MARK_SORTED, k)


def quick_sort(arr: list[int]) -> Iterator[tuple]:
    """Yield ops for quick sort (Lomuto partition, last element as pivot)."""
    n = len(arr)

    def _partition(lo: int, hi: int) -> int:
        """Return final pivot position. Yields visual ops."""
        pivot_idx = hi
        yield (OP_LINE, 3)  # pivot = a[hi]
        i = lo - 1
        for j in range(lo, hi):
            yield (OP_LINE, 4)  # for j in range(...)
            yield (OP_COMPARE, j, pivot_idx)
            if arr[j] <= arr[pivot_idx]:
                i += 1
                if i != j:
                    yield (OP_LINE, 5)  # swap(a, i, j)
                    yield (OP_SWAP, i, j)
                    arr[i], arr[j] = arr[j], arr[i]
        # Place pivot into position i+1
        if i + 1 != pivot_idx:
            yield (OP_SWAP, i + 1, pivot_idx)
            arr[i + 1], arr[pivot_idx] = arr[pivot_idx], arr[i + 1]
        pivot_final = i + 1
        yield (OP_MARK_SORTED, pivot_final)
        return pivot_final

    def _qs(lo: int, hi: int):
        if lo >= hi:
            if lo == hi:
                yield (OP_MARK_SORTED, lo)
            return
        yield (OP_LINE, 2)  # if lo >= hi: return
        # _partition is itself a generator that returns the pivot.
        # We can't get a return value from `yield from` cleanly with
        # mixed yields, so we drive it directly.
        gen = _partition(lo, hi)
        try:
            while True:
                op = next(gen)
                yield op
        except StopIteration as e:
            p = e.value
        yield (OP_LINE, 6)  # _qs(lo, p-1); _qs(p+1, hi)
        yield from _qs(lo, p - 1)
        yield from _qs(p + 1, hi)

    yield from _qs(0, n - 1)
    # Make sure everything ends up marked (covers single-element bases).
    for k in range(n):
        yield (OP_MARK_SORTED, k)


def heap_sort(arr: list[int]) -> Iterator[tuple]:
    """Yield ops for heap sort.

    Standard two-phase: heapify (sift down), then repeatedly swap root
    with last and sift down.
    """
    n = len(arr)

    def _sift_down(start: int, end: int):
        root = start
        while True:
            child = 2 * root + 1
            if child >= end:
                break
            yield (OP_LINE, 2)  # if not (child+1 < end and a[child] < a[child+1]): child++
            if child + 1 < end and arr[child] < arr[child + 1]:
                child += 1
            yield (OP_COMPARE, root, child)
            if arr[root] < arr[child]:
                yield (OP_SWAP, root, child)
                arr[root], arr[child] = arr[child], arr[root]
                root = child
            else:
                break

    # Phase 1: build max-heap
    yield (OP_LINE, 5)  # for start in reversed range...
    for start in range(n // 2 - 1, -1, -1):
        yield from _sift_down(start, n)

    # Phase 2: sort. Move max to end, shrink heap.
    for end in range(n - 1, 0, -1):
        yield (OP_LINE, 7)  # swap(a, 0, end); end -= 1
        yield (OP_SWAP, 0, end)
        arr[0], arr[end] = arr[end], arr[0]
        yield (OP_MARK_SORTED, end)
        yield from _sift_down(0, end)
    yield (OP_MARK_SORTED, 0)


# ─────────────────────────────────────────────────────────────────────
# Algorithm registry — populated as more algorithms land in later phases.
# ─────────────────────────────────────────────────────────────────────

ALGORITHMS: dict[str, Callable[[list[int]], Iterator[tuple]]] = {
    "bubble":    bubble_sort,
    "selection": selection_sort,
    "insertion": insertion_sort,
    "merge":     merge_sort,
    "quick":     quick_sort,
    "heap":      heap_sort,
}

ALGO_DISPLAY: dict[str, str] = {
    "bubble":    "Bubble sort",
    "selection": "Selection sort",
    "insertion": "Insertion sort",
    "merge":     "Merge sort",
    "quick":     "Quick sort",
    "heap":      "Heap sort",
}

PSEUDO_CODE: dict[str, list[str]] = {
    "bubble": [
        "function bubble_sort(a):",          # 0
        "  n = length(a)",                    # 1
        "  for i in 0 .. n-2:",               # 2  (compare happens here)
        "    for j in 0 .. n-2-i:",            # 3
        "      if a[j] > a[j+1]:",             # 4  (swap happens here)
        "        swap a[j], a[j+1]",           # 5
        "    if not swapped: break",           # 6
    ],
    "selection": [
        "function selection_sort(a):",        # 0
        "  n = length(a)",                    # 1
        "  for i in 0 .. n-2:",               # 2
        "    min = i",                        # 3
        "    for j in i+1 .. n-1:",           # 4
        "      if a[j] < a[min]: min = j",    # 5
        "    swap a[i], a[min]",              # 6
    ],
    "insertion": [
        "function insertion_sort(a):",        # 0
        "  n = length(a)",                    # 1
        "  for i in 1 .. n-1:",               # 2
        "    key = a[i]",                     # 3
        "    while j > 0 and a[j-1] > key:",  # 4
        "      a[j-1], a[j] = a[j], a[j-1]",  # 5
    ],
    "merge": [
        "function merge_sort(a, lo, hi):",    # 0
        "  if hi - lo <= 1: return",          # 1
        "  mid = (lo + hi) / 2",              # 2
        "  merge_sort(a, lo, mid)",           # 3
        "  merge_sort(a, mid, hi)",           # 4
        "  merge(a, lo, mid, hi)",            # 5
        "    i=lo, j=mid",                    # 6
        "    while i < mid and j < hi:",      # 7
        "      a[k] = smaller(a[i], a[j])",   # 8
    ],
    "quick": [
        "function quick_sort(a, lo, hi):",    # 0
        "  if lo >= hi: return",              # 1
        "  pivot = a[hi]",                    # 2
        "  for j in lo .. hi-1:",             # 3
        "    if a[j] <= pivot:",              # 4
        "      swap a[i], a[j]",              # 5
        "  swap a[i+1], a[hi]",               # 6
    ],
    "heap": [
        "function heap_sort(a):",             # 0
        "  sift_down(a, root, end):",         # 1
        "    child = 2*root + 1",             # 2
        "    pick larger child",              # 3
        "    if a[child] > a[root]: swap",    # 4
        "  for start in n/2-1 .. 0:",         # 5
        "    sift_down(a, start, n)",         # 6
        "  swap a[0], a[end]; end--",         # 7
    ],
}


# ─────────────────────────────────────────────────────────────────────
# State + Runner
# ─────────────────────────────────────────────────────────────────────

@dataclass
class RunStats:
    """Stats for a single algorithm run."""
    comparisons: int = 0
    writes: int = 0           # writes == swaps for in-place algos; mergesort counts aux writes
    started_at: float = 0.0
    op_index: int = 0

    def reset(self) -> None:
        self.comparisons = 0
        self.writes = 0
        self.op_index = 0
        self.started_at = time.perf_counter()


@dataclass
class Runner:
    """Drives an algorithm generator, paces it against wall-clock."""
    name: str
    algo: Callable[[list[int]], Iterator[tuple]]
    arr: list[int]
    speed_ops_per_sec: float = 20.0
    paused: bool = False
    finished: bool = False
    stats: RunStats = field(default_factory=RunStats)

    # Per-op UI state — read by the renderer.
    highlight_compare: set[int] = field(default_factory=set)
    highlight_swap: set[int] = field(default_factory=set)
    sorted_indices: set[int] = field(default_factory=set)
    current_line: int = -1

    # Internal
    _gen: Iterator[tuple] | None = None
    _last_op_at: float = 0.0

    def setup(self) -> None:
        self._gen = self.algo(self.arr)
        self.paused = False
        self.finished = False
        self.stats.reset()
        self.highlight_compare.clear()
        self.highlight_swap.clear()
        self.sorted_indices.clear()
        self.current_line = -1
        self._last_op_at = time.perf_counter()

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def step_once(self) -> None:
        """Advance one op (only valid while paused)."""
        if not self.finished and self._gen is not None:
            self._consume_one_op()

    def reset_with_same_array(self) -> None:
        self.setup()

    def tick(self) -> None:
        """Called every frame; advance ops based on speed."""
        if self.finished or self.paused or self._gen is None:
            return

        now = time.perf_counter()
        ops_to_do = int((now - self._last_op_at) * self.speed_ops_per_sec)
        # Always do at least one op per frame to avoid stalls at slow speeds.
        ops_to_do = max(ops_to_do, 1)

        for _ in range(ops_to_do):
            if not self._consume_one_op():
                break
        self._last_op_at = now

    def _consume_one_op(self) -> bool:
        """Consume one op; returns False if generator is exhausted."""
        assert self._gen is not None
        try:
            op = next(self._gen)
        except StopIteration:
            self.finished = True
            self.current_line = -1
            self.highlight_compare.clear()
            self.highlight_swap.clear()
            return False

        kind = op_kind(op)
        self.stats.op_index += 1

        # Clear frame-only highlights.
        self.highlight_compare.clear()
        self.highlight_swap.clear()

        if kind == OP_COMPARE:
            _, i, j = op
            self.highlight_compare.update([i, j])
            self.stats.comparisons += 1
        elif kind == OP_SWAP:
            _, i, j = op
            self.highlight_swap.update([i, j])
            self.stats.writes += 1
        elif kind == OP_WRITE:
            _, i, value = op
            self.highlight_swap.add(i)
            self.arr[i] = value
            self.stats.writes += 1
        elif kind == OP_MARK_SORTED:
            _, i = op
            self.sorted_indices.add(i)
        elif kind == OP_LINE:
            _, line = op
            self.current_line = line

        return True

    def elapsed_ms(self) -> int:
        if self.stats.started_at == 0.0:
            return 0
        if self.finished:
            return int((self.stats.started_at + self.stats.op_index / max(self.speed_ops_per_sec, 0.001)
                        - self.stats.started_at) * 1000)
        return int((time.perf_counter() - self.stats.started_at) * 1000)


# ─────────────────────────────────────────────────────────────────────
# Renderer — pygame UI: bars, stats, button bar, pseudo-code panel.
# ─────────────────────────────────────────────────────────────────────

# Colors
BG = (18, 18, 24)
BG_PANEL = (24, 24, 32)
BAR = (180, 180, 200)
BAR_COMPARE = (240, 220, 80)
BAR_SWAP = (240, 80, 80)
BAR_SORTED = (80, 220, 120)
TEXT = (220, 220, 220)
TEXT_DIM = (150, 150, 160)
TEXT_FAINT = (100, 100, 110)
ACCENT = (100, 200, 240)
ACCENT_DIM = (60, 130, 160)
PANEL_LINE = (255, 235, 100)
PANEL_LINE_BG = (60, 60, 90)
BUTTON = (50, 55, 75)
BUTTON_HOVER = (75, 85, 110)
BUTTON_ACTIVE = (90, 170, 220)
WINNER = (255, 215, 80)


SCREEN_W = 1280
SCREEN_H = 720

# Layout regions (vertical stripes)
TOP_BAR_H = 28           # title/status
STATS_BAR_H = 26         # counters
BUTTON_BAR_H = 36        # on-screen buttons
PSEUDO_PANEL_H = 150     # bottom panel for code
BAR_AREA_TOP = TOP_BAR_H + STATS_BAR_H + BUTTON_BAR_H + 12
BAR_AREA_BOTTOM = SCREEN_H - PSEUDO_PANEL_H - 8

# Speed presets (ops/sec)
SPEED_PRESETS = [0.5, 1, 2, 5, 10, 20, 50, 100, 250, 1000]
SIZE_PRESETS = [10, 25, 50, 75, 100, 150, 250]

# Algorithm ordering (for keybindings 1-6)
ALGO_ORDER = ["bubble", "selection", "insertion", "merge", "quick", "heap"]


def make_array(size: int, seed: int | None = None, shuffled: bool = True) -> list[int]:
    rng = random.Random(seed)
    arr = list(range(1, size + 1))
    if shuffled:
        rng.shuffle(arr)
    return arr


# Alias for clarity at call sites; renderer prefers explicit shuffled args.
make_shuffled = lambda size, seed=None: make_array(size, seed, shuffled=True)


def draw_bars(surface, arr: list[int], run_state: dict,
              x: int, y: int, w: int, h: int) -> None:
    """Draw bars for one runner's view.

    run_state carries highlights/sorted/line for that runner.
    """
    n = len(arr)
    if n == 0:
        return
    bar_w = max(1, w // n)
    value_max = max(arr) if arr else 1
    pad_x = (w - bar_w * n) // 2

    for i in range(n):
        bx = x + pad_x + i * bar_w
        val = arr[i]
        bh = max(1, int(h * (val / value_max)))
        by = y + h - bh
        color = BAR
        if i in run_state["sorted"]:
            color = BAR_SORTED
        if i in run_state["swap"]:
            color = BAR_SWAP
        elif i in run_state["compare"]:
            color = BAR_COMPARE
        pygame.draw.rect(surface, color, (bx, by, max(1, bar_w - 1), bh))


def draw_text(surface, text: str, x: int, y: int,
              color=TEXT, size: int = 16, font=None,
              center: bool = False) -> pygame.Rect:
    f = font or pygame.font.SysFont("Menlo", size)
    surf = f.render(text, True, color)
    rect = surf.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(surf, rect)
    return rect


def measure_text(text: str, size: int = 16, font=None) -> tuple[int, int]:
    f = font or pygame.font.SysFont("Menlo", size)
    return f.size(text)


def run_state_from(runner: Runner) -> dict:
    """Snapshot the per-frame UI state from a runner."""
    return {
        "compare": runner.highlight_compare,
        "swap":    runner.highlight_swap,
        "sorted":  runner.sorted_indices,
        "line":    runner.current_line,
    }


# ─── Pseudo-code panel ─────────────────────────────────────────────

class PseudoPanel:
    """Renders the algorithm's pseudo-code with the active line highlighted."""

    LINE_H = 16
    FONT_SIZE = 14

    def __init__(self, algo: str):
        self.set_algo(algo)

    def set_algo(self, algo: str) -> None:
        self.algo = algo
        self.lines = PSEUDO_CODE.get(algo, [])
        self.font = pygame.font.SysFont("Menlo", self.FONT_SIZE)

    def draw(self, surface, x: int, y: int, w: int, h: int,
             current_line: int) -> None:
        # Background
        pygame.draw.rect(surface, BG_PANEL, (x, y, w, h))
        pygame.draw.line(surface, ACCENT_DIM, (x, y), (x + w, y), 1)

        # Title
        title_font = pygame.font.SysFont("Menlo", 13)
        title = f"  pseudo-code — {ALGO_DISPLAY.get(self.algo, self.algo)} (P toggles, T race)"
        surface.blit(title_font.render(title, True, TEXT_DIM), (x + 8, y + 4))

        # Code lines
        if not self.lines:
            return
        code_y = y + 24
        clip = pygame.Rect(x, code_y, w, h - 28)
        old_clip = surface.get_clip()
        surface.set_clip(clip)
        try:
            for i, line in enumerate(self.lines):
                line_y = code_y + i * self.LINE_H
                if line_y + self.LINE_H < code_y or line_y > code_y + h:
                    continue
                if i == current_line:
                    pygame.draw.rect(surface, PANEL_LINE_BG,
                                     (x + 4, line_y - 2, w - 8, self.LINE_H))
                    color = PANEL_LINE
                else:
                    color = TEXT_DIM if i < 3 else TEXT_FAINT
                surface.blit(self.font.render(line, True, color),
                             (x + 12, line_y))
        finally:
            surface.set_clip(old_clip)


# ─── Button bar ────────────────────────────────────────────────────

class Button:
    def __init__(self, label: str, x: int, y: int, w: int, h: int,
                 hotkey: str | None = None):
        self.label = label
        self.rect = pygame.Rect(x, y, w, h)
        self.hotkey = hotkey
        self.hover = False
        self.active = False

    def draw(self, surface, font) -> None:
        color = BUTTON_ACTIVE if self.active else (BUTTON_HOVER if self.hover else BUTTON)
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        # 1px highlight on top edge for definition
        pygame.draw.line(surface, ACCENT_DIM, self.rect.topleft,
                         self.rect.topright, 1)
        # Centered label
        text_color = (10, 10, 20) if self.active else TEXT
        text_surf = font.render(self.label, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def hit(self, mx: int, my: int) -> bool:
        return self.rect.collidepoint(mx, my)


def build_button_bar(width: int, top: int) -> list[Button]:
    labels = [
        ("Play",   "Space"),
        ("Step",   "."),
        ("Reset",  "R"),
        ("Shuffle", "N"),
        ("Size-",  "-"),
        ("Size+",  "+"),
        ("Slower", "["),
        ("Faster", "]"),
        ("Panel",  "P"),
        ("Race",   "T"),
    ]
    pad = 6
    btn_h = BUTTON_BAR_H - 6
    # Lay out labels with their hotkey captions.
    btns = []
    x = pad
    for label, hot in labels:
        text = f"{label} [{hot}]" if hot else label
        # Compute width: roughly 7 pixels per char + 16 for padding
        w = max(72, len(text) * 7 + 16)
        if x + w + pad > width:
            break
        btns.append(Button(text, x, top + 3, w, btn_h, hotkey=hot))
        x += w + pad
    return btns


def find_button_by_hotkey(btns: list[Button], hot: str) -> Button | None:
    for b in btns:
        if b.hotkey and b.hotkey.lower() == hot.lower():
            return b
    return None


# ─── Stats overlay ─────────────────────────────────────────────────

def draw_stats_strip(surface, runner, left: int, top: int,
                     width: int, font, prefix: str = "") -> None:
    """Draw a single-runner's stats strip near the top of the bar area."""
    elapsed_ms = runner.elapsed_ms()
    pieces = [
        f"{prefix}algo: {ALGO_DISPLAY.get(runner.name, runner.name)}",
        f"compares: {runner.stats.comparisons}",
        f"writes: {runner.stats.writes}",
        f"ops: {runner.stats.op_index}",
        f"speed: {runner.speed_ops_per_sec:.1f}/s",
        f"elapsed: {elapsed_ms} ms",
    ]
    status = "DONE" if runner.finished else ("PAUSED" if runner.paused else "PLAYING")
    pieces.append(f"status: {status}")

    x = left + 8
    for p in pieces:
        text_color = ACCENT if p.startswith(f"{prefix}status: PLAYING") else TEXT
        text_color = WINNER if p.startswith(f"{prefix}status: DONE") and runner.finished else text_color
        draw_text(surface, p, x, top, color=text_color, size=14, font=font)
        x += measure_text(p, 14, font)[0] + 16


def draw_top_strip(surface, width: int, controls_line: str, font) -> None:
    """Top bar with global controls and (race) summary."""
    draw_text(surface, "Sorting Visualizer", 12, 6, TEXT, 16, font)
    draw_text(surface, controls_line, width - 380, 6, TEXT_DIM, 14, font)


# ─────────────────────────────────────────────────────────────────────
# Application state + main loop
# ─────────────────────────────────────────────────────────────────────

@dataclass
class AppState:
    """UI state shared by main loop."""
    runner: Runner              # solo mode (active)
    left_runner: Runner = field(default_factory=lambda: None)   # type: ignore
    right_runner: Runner = field(default_factory=lambda: None)  # type: ignore
    algo_index: int = 0
    size_index: int = 2   # default 50
    speed_index: int = 5   # default 20 ops/sec
    show_panel: bool = True
    race_mode: bool = False
    panel: PseudoPanel | None = None
    left_panel: PseudoPanel | None = None
    right_panel: PseudoPanel | None = None
    buttons: list[Button] = field(default_factory=list)
    font: pygame.font.Font | None = None
    big_font: pygame.font.Font | None = None
    title_font: pygame.font.Font | None = None
    # Race-mode winner
    winner: str | None = None   # 'left', 'right', or None
    winner_time: float = 0.0
    # Rate control per runner (only used in race mode)
    left_speed_index: int = 5
    right_speed_index: int = 5

    @property
    def algo(self) -> str:
        return ALGO_ORDER[self.algo_index]

    @property
    def size(self) -> int:
        return SIZE_PRESETS[self.size_index]

    @property
    def speed(self) -> float:
        return SPEED_PRESETS[self.speed_index]

    def set_algo(self, idx: int) -> None:
        self.algo_index = idx % len(ALGO_ORDER)
        new_algo_name = self.algo
        self.new_array(shuffled=True)
        self.runner.speed_ops_per_sec = self.speed
        if self.panel:
            self.panel.set_algo(new_algo_name)

    def set_race_algorithm(self, side: str, idx: int) -> None:
        """Switch the algorithm of one race side. side is 'left' or 'right'."""
        if not self.race_mode:
            return
        new_algo = ALGO_ORDER[idx % len(ALGO_ORDER)]
        if side == 'left':
            self.left_runner = Runner(name=new_algo, algo=ALGORITHMS[new_algo],
                                       arr=list(self.left_runner.arr),
                                       speed_ops_per_sec=self.speed_for('left'))
            self.left_runner.setup()
            if self.left_panel:
                self.left_panel.set_algo(new_algo)
        else:
            self.right_runner = Runner(name=new_algo, algo=ALGORITHMS[new_algo],
                                        arr=list(self.right_runner.arr),
                                        speed_ops_per_sec=self.speed_for('right'))
            self.right_runner.setup()
            if self.right_panel:
                self.right_panel.set_algo(new_algo)

    def speed_for(self, side: str) -> float:
        idx = self.left_speed_index if side == 'left' else self.right_speed_index
        return SPEED_PRESETS[idx]

    def new_array(self, shuffled: bool = True) -> None:
        arr = make_array(self.size, shuffled=shuffled)
        self.runner.arr = arr
        self.runner.setup()
        if self.race_mode and self.left_runner and self.right_runner:
            # Both sides get the same starting array.
            self.left_runner.arr = list(arr)
            self.left_runner.setup()
            self.right_runner.arr = list(arr)
            self.right_runner.setup()
            self.winner = None
            self.winner_time = 0.0

    def change_size(self, delta: int) -> None:
        self.size_index = max(0, min(len(SIZE_PRESETS) - 1, self.size_index + delta))
        self.new_array(shuffled=True)

    def change_speed(self, delta: int) -> None:
        self.speed_index = max(0, min(len(SPEED_PRESETS) - 1, self.speed_index + delta))
        if self.race_mode:
            self.left_runner.speed_ops_per_sec = SPEED_PRESETS[self.left_speed_index]
            self.right_runner.speed_ops_per_sec = SPEED_PRESETS[self.right_speed_index]
        else:
            self.runner.speed_ops_per_sec = self.speed

    def change_race_speed(self, side: str, delta: int) -> None:
        attr = 'left_speed_index' if side == 'left' else 'right_speed_index'
        cur = getattr(self, attr)
        cur = max(0, min(len(SPEED_PRESETS) - 1, cur + delta))
        setattr(self, attr, cur)
        if side == 'left':
            self.left_runner.speed_ops_per_sec = SPEED_PRESETS[cur]
        else:
            self.right_runner.speed_ops_per_sec = SPEED_PRESETS[cur]


# ── Race mode layout ──────────────────────────────────────────────

RACE_PANEL_W = SCREEN_W // 2
RACE_BAR_BOTTOM = SCREEN_H - PSEUDO_PANEL_H - 8

def draw_race_layout(surface, left: Runner, right: Runner,
                     left_panel: PseudoPanel, right_panel: PseudoPanel,
                     app: AppState) -> None:
    """Draw two side-by-side race panes with their pseudo-code panels."""
    divider_x = RACE_PANEL_W
    # Left pane
    pygame.draw.rect(surface, BG, (0, BAR_AREA_TOP, RACE_PANEL_W,
                                  RACE_BAR_BOTTOM - BAR_AREA_TOP))
    draw_bars(surface, left.arr, run_state_from(left),
              0, BAR_AREA_TOP, RACE_PANEL_W - 4,
              RACE_BAR_BOTTOM - BAR_AREA_TOP)
    if app.show_panel:
        left_panel.draw(surface, 0, SCREEN_H - PSEUDO_PANEL_H,
                        RACE_PANEL_W, PSEUDO_PANEL_H,
                        left.current_line)
    draw_text(surface, f"L: {ALGO_DISPLAY.get(left.name, left.name)} "
                       f"(compares: {left.stats.comparisons}, writes: {left.stats.writes})",
              8, BAR_AREA_TOP - 22, ACCENT, 14, app.font)

    # Right pane
    draw_bars(surface, right.arr, run_state_from(right),
              divider_x + 4, BAR_AREA_TOP, RACE_PANEL_W - 4,
              RACE_BAR_BOTTOM - BAR_AREA_TOP)
    if app.show_panel:
        right_panel.draw(surface, divider_x, SCREEN_H - PSEUDO_PANEL_H,
                         RACE_PANEL_W, PSEUDO_PANEL_H,
                         right.current_line)
    draw_text(surface, f"R: {ALGO_DISPLAY.get(right.name, right.name)} "
                       f"(compares: {right.stats.comparisons}, writes: {right.stats.writes})",
              divider_x + 8, BAR_AREA_TOP - 22, ACCENT, 14, app.font)

    # Divider
    pygame.draw.line(surface, ACCENT_DIM,
                     (divider_x, BAR_AREA_TOP - 6),
                     (divider_x, SCREEN_H - 4), 1)

    # Winner overlay
    if app.winner == 'left' and not right.finished:
        winner_surf = app.big_font.render("\u25b6 WINNER", True, WINNER)
        surface.blit(winner_surf, (24, BAR_AREA_TOP + 24))
    elif app.winner == 'right' and not left.finished:
        winner_surf = app.big_font.render("\u25b6 WINNER", True, WINNER)
        surface.blit(winner_surf, (divider_x + 24, BAR_AREA_TOP + 24))
    elif app.winner == 'tie':
        # Both finished simultaneously.
        mid_x = SCREEN_W // 2 - 60
        tie_surf = app.big_font.render("TIE", True, WINNER)
        surface.blit(tie_surf, (mid_x, BAR_AREA_TOP + 24))

    # Delta indicator (always shown in race mode for a quick read)
    if app.winner:
        delta = abs(left.stats.comparisons - right.stats.comparisons)
        delta_str = (f"\u0394 compares: {delta}  "
                     f"({ALGO_DISPLAY.get(left.name, left.name)} vs "
                     f"{ALGO_DISPLAY.get(right.name, right.name)})")
        draw_text(surface, delta_str, SCREEN_W // 2 - 180, 6, WINNER, 13, app.font)


# ── Race-mode setup/tick ──────────────────────────────────────────

def enter_race_mode(app: AppState, left_algo: str, right_algo: str) -> None:
    """Initialize two runners sharing the same input array."""
    arr = make_array(app.size, shuffled=True)
    arr_copy_l = list(arr)
    arr_copy_r = list(arr)
    speed = app.speed
    left = Runner(name=left_algo, algo=ALGORITHMS[left_algo],
                  arr=arr_copy_l, speed_ops_per_sec=speed)
    right = Runner(name=right_algo, algo=ALGORITHMS[right_algo],
                   arr=arr_copy_r, speed_ops_per_sec=speed)
    left.setup()
    right.setup()
    app.left_runner = left
    app.right_runner = right
    app.left_panel = PseudoPanel(left_algo)
    app.right_panel = PseudoPanel(right_algo)
    app.race_mode = True
    app.winner = None
    app.winner_time = 0.0


def tick_race(app: AppState) -> None:
    if not app.race_mode or app.left_runner is None or app.right_runner is None:
        return
    # Pause/resume both via space.
    if app.left_runner.paused and app.right_runner.paused:
        return
    if not app.left_runner.finished:
        app.left_runner.tick()
    if not app.right_runner.finished:
        app.right_runner.tick()
    # Detect winner
    if app.winner is None:
        if app.left_runner.finished and not app.right_runner.finished:
            app.winner = 'left'
            app.winner_time = time.perf_counter()
        elif app.right_runner.finished and not app.left_runner.finished:
            app.winner = 'right'
            app.winner_time = time.perf_counter()
        elif app.left_runner.finished and app.right_runner.finished:
            # Tie.
            app.winner = 'tie'
            app.winner_time = time.perf_counter()


def toggle_race_pause(app: AppState) -> None:
    if not app.race_mode:
        app.runner.toggle_pause()
        return
    new = not app.left_runner.paused
    app.left_runner.paused = new
    app.right_runner.paused = new


def step_race_once(app: AppState) -> None:
    if not app.race_mode:
        if app.runner.paused or app.runner.finished:
            if app.runner.finished:
                app.runner.setup()
            app.runner.step_once()
        return
    if not (app.left_runner.paused and app.right_runner.paused):
        return  # only step while paused
    if not app.left_runner.finished:
        app.left_runner.step_once()
    if not app.right_runner.finished:
        app.right_runner.step_once()


def render_one_pane(surface, runner: Runner, panel: PseudoPanel,
                    app: AppState) -> None:
    """Render the bars and (optionally) pseudo-code panel for a single runner."""
    draw_bars(surface, runner.arr, run_state_from(runner),
              0, BAR_AREA_TOP, SCREEN_W,
              BAR_AREA_BOTTOM - BAR_AREA_TOP)

    if app.show_panel:
        panel.draw(surface, 0, SCREEN_H - PSEUDO_PANEL_H,
                   SCREEN_W, PSEUDO_PANEL_H,
                   runner.current_line)


def controls_line(app: AppState) -> str:
    if app.race_mode:
        return ("[Space]play/pause  [.]step  [R]reset (race)  [1-6]pick L  "
                "[Shift 1-6]pick R  [,/.]L speed  [</>]R speed  "
                "[P]panel  [T]race-off  [Q]quit")
    return ("[Space]play  [.]step  [R]reset  [N]new  [1-6]algo  [-+]size  "
            "[[ ]]speed  [P]panel  [T]race  [Q]quit")


def _resolve_initial_algo(name: str) -> str:
    return name if name in ALGO_ORDER else "bubble"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=None)
    parser.add_argument("--speed", type=float, default=None)
    parser.add_argument("--algo", type=str, default="bubble",
                        choices=ALGO_ORDER)
    parser.add_argument("--no-panel", action="store_true")
    parser.add_argument("--race", action="store_true",
                        help="Start in race mode")
    parser.add_argument("--race-left", type=str, default="quick",
                        help="Algorithm for left runner in race mode")
    parser.add_argument("--race-right", type=str, default="merge",
                        help="Algorithm for right runner in race mode")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_caption("Sorting Visualizer")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Menlo", 16)
    big_font = pygame.font.SysFont("Menlo", 22, bold=True)
    title_font = pygame.font.SysFont("Menlo", 18, bold=True)

    init_size = args.size if args.size is not None else SIZE_PRESETS[2]
    init_speed = args.speed if args.speed is not None else SPEED_PRESETS[5]
    arr = make_array(init_size, shuffled=True)
    algo_fn = ALGORITHMS[_resolve_initial_algo(args.algo)]
    runner = Runner(name=_resolve_initial_algo(args.algo), algo=algo_fn, arr=arr,
                    speed_ops_per_sec=init_speed)
    runner.setup()

    app = AppState(runner=runner, show_panel=not args.no_panel)
    if args.algo in ALGO_ORDER:
        app.algo_index = ALGO_ORDER.index(args.algo)
    if init_size in SIZE_PRESETS:
        app.size_index = SIZE_PRESETS.index(init_size)
    if init_speed in SPEED_PRESETS:
        app.speed_index = SPEED_PRESETS.index(init_speed)
    app.panel = PseudoPanel(args.algo)
    app.buttons = build_button_bar(SCREEN_W, TOP_BAR_H + STATS_BAR_H)
    app.font = font
    app.big_font = big_font
    app.title_font = title_font

    if args.race:
        left = _resolve_initial_algo(args.race_left)
        right = _resolve_initial_algo(args.race_right)
        enter_race_mode(app, left, right)

    running = True
    mouse_pos = (0, 0)
    quit_requested = False

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEMOTION:
                mouse_pos = event.pos
                for b in app.buttons:
                    b.hover = b.hit(*mouse_pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for b in app.buttons:
                    if b.hit(*mouse_pos):
                        handle_button(app, b.hotkey)
            elif event.type == pygame.KEYDOWN:
                if handle_key(app, event.key, event.mod):
                    quit_requested = True
                    running = False

        if app.race_mode:
            tick_race(app)
        else:
            app.runner.tick()

        # ─── Draw ───
        screen.fill(BG)

        draw_text(screen, "Sorting Visualizer", 12, 6, TEXT, 16, font)
        draw_text(screen, controls_line(app), 220, 8, TEXT_DIM, 14, font)

        if not app.race_mode:
            draw_stats_strip(screen, app.runner, 0, TOP_BAR_H,
                             SCREEN_W, font)
        else:
            # In race mode, draw a slim stats line per side, above the bars.
            draw_text(screen,
                      f"L: {app.left_runner.name} "
                      f"({app.left_runner.stats.comparisons}c / "
                      f"{app.left_runner.stats.writes}w / "
                      f"{SPEED_PRESETS[app.left_speed_index]}/s) "
                      f"status: {'DONE' if app.left_runner.finished else 'PLAYING' if not app.left_runner.paused else 'PAUSED'}",
                      12, TOP_BAR_H + 6, ACCENT, 13, font)
            draw_text(screen,
                      f"R: {app.right_runner.name} "
                      f"({app.right_runner.stats.comparisons}c / "
                      f"{app.right_runner.stats.writes}w / "
                      f"{SPEED_PRESETS[app.right_speed_index]}/s) "
                      f"status: {'DONE' if app.right_runner.finished else 'PLAYING' if not app.right_runner.paused else 'PAUSED'}",
                      RACE_PANEL_W + 12, TOP_BAR_H + 6, ACCENT, 13, font)

        # Button bar
        button_top = TOP_BAR_H + STATS_BAR_H
        for b in app.buttons:
            if b.hotkey == "Space":
                if app.race_mode:
                    b.active = (not app.left_runner.paused and not app.left_runner.finished)
                else:
                    b.active = not app.runner.paused and not app.runner.finished
            elif b.hotkey == "P":
                b.active = app.show_panel
            elif b.hotkey == "T":
                b.active = app.race_mode
            b.draw(screen, font)

        # Bars + (optional) panel
        if not app.race_mode:
            render_one_pane(screen, app.runner, app.panel, app)
        else:
            draw_race_layout(screen, app.left_runner, app.right_runner,
                             app.left_panel, app.right_panel, app)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    if quit_requested:
        return 0
    return 0


def handle_button(app: AppState, hot: str | None) -> None:
    """Map a button hotkey to a key-style action."""
    if not hot:
        return
    # Synthesize a fake event.key mapping.
    keymap = {
        "Space": pygame.K_SPACE, ".": pygame.K_PERIOD,
        "R": pygame.K_r, "N": pygame.K_n,
        "-": pygame.K_MINUS, "+": pygame.K_PLUS,
        "[": pygame.K_LEFTBRACKET, "]": pygame.K_RIGHTBRACKET,
        "P": pygame.K_p, "T": pygame.K_t, "Q": pygame.K_q,
    }
    key = keymap.get(hot)
    if key is not None:
        handle_key(app, key, 0)


def handle_key(app: AppState, key: int, mod: int) -> bool:
    """Dispatch a key press. Return True if the app should quit."""
    # Quit
    if key in (pygame.K_q, pygame.K_ESCAPE):
        return True

    # Race mode global toggle: T enters/exits race.
    if key == pygame.K_t and not (mod & pygame.KMOD_SHIFT):
        if app.race_mode:
            # Exit race, keep left as primary.
            app.race_mode = False
            app.runner = app.left_runner
            app.panel = app.left_panel
            app.algo_index = ALGO_ORDER.index(app.left_runner.name)
        else:
            # Enter race with current algo on left and a quick pick on right.
            enter_race_mode(app, app.algo, "quick")
        return False

    if app.race_mode:
        return _handle_key_race(app, key, mod)

    # ── Solo-mode keys ──
    if key == pygame.K_SPACE:
        app.runner.toggle_pause()
    elif key == pygame.K_PERIOD:
        if app.runner.finished:
            app.runner.setup()
        else:
            app.runner.step_once()
    elif key == pygame.K_r:
        app.runner.reset_with_same_array()
    elif key == pygame.K_n:
        app.new_array(shuffled=True)
    elif key == pygame.K_MINUS:
        app.change_size(-1)
    elif key in (pygame.K_PLUS, pygame.K_EQUALS):
        app.change_size(+1)
    elif key == pygame.K_LEFTBRACKET:
        app.change_speed(-1)
    elif key == pygame.K_RIGHTBRACKET:
        app.change_speed(+1)
    elif key == pygame.K_p:
        app.show_panel = not app.show_panel
    elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6):
        new_idx = key - pygame.K_1
        if 0 <= new_idx < len(ALGO_ORDER):
            app.set_algo(new_idx)
    return False


def _handle_key_race(app: AppState, key: int, mod: int) -> bool:
    """Race-mode key handler."""
    if key == pygame.K_SPACE:
        toggle_race_pause(app)
    elif key == pygame.K_PERIOD:
        step_race_once(app)
    elif key == pygame.K_r:
        # Reset race: rebuild both with same fresh array.
        arr = make_array(app.size, shuffled=True)
        app.left_runner.arr = list(arr); app.left_runner.setup()
        app.right_runner.arr = list(arr); app.right_runner.setup()
        app.winner = None
        app.winner_time = 0.0
    elif key == pygame.K_n:
        app.new_array(shuffled=True)
    elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6):
        if mod & pygame.KMOD_SHIFT:
            # Right side (no Shift handling here, since we don't have a K_EXCLAIM; instead use letter keys)
            return False
        new_idx = key - pygame.K_1
        if 0 <= new_idx < len(ALGO_ORDER):
            app.set_race_algorithm('left', new_idx)
    elif key in (pygame.K_z, pygame.K_x, pygame.K_c, pygame.K_v, pygame.K_b, pygame.K_m):
        # Right side algorithm: Z=1, X=2, ... M=6
        new_idx = key - pygame.K_z
        if 0 <= new_idx < len(ALGO_ORDER):
            app.set_race_algorithm('right', new_idx)
    elif key in (pygame.K_COMMA, pygame.K_PERIOD):
        # Comma slows left, period speeds left
        delta = -1 if key == pygame.K_COMMA else +1
        app.change_race_speed('left', delta)
    elif key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
        # Symmetric for right
        delta = -1 if key == pygame.K_LEFTBRACKET else +1
        app.change_race_speed('right', delta)
    elif key == pygame.K_p:
        app.show_panel = not app.show_panel
    return False


if __name__ == "__main__":
    sys.exit(main())
