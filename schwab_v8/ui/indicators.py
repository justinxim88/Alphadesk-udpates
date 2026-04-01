"""
PD/PM/OR Levels + EMA 9/20/50 Indicator
Ported from Pine Script by justinxim

Draws on pyqtgraph PlotWidget:
- Previous Day High/Low (red/green boxes from wick to body edge)
- Premarket High/Low (purple/blue boxes)
- Opening Range High/Low (lime/orange horizontal lines)
- EMA 9, 20, 50
"""

import pyqtgraph as pg
from pyqtgraph import QtCore, QtGui
from PyQt6.QtGui import QColor
from datetime import datetime, timezone, time as dtime, timedelta
import numpy as np


GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
YELLOW = "#d29922"
PURPLE = "#8957e5"
LIME   = "#39d353"
ORANGE = "#f0883e"


def calc_ema(values, period):
    result = [None] * len(values)
    k = 2 / (period + 1)
    for i in range(len(values)):
        if i < period - 1:
            continue
        if i == period - 1:
            result[i] = sum(values[:period]) / period
        else:
            result[i] = values[i] * k + result[i-1] * (1 - k)
    return result


def parse_dt(dt_str: str) -> datetime:
    """Parse ISO datetime string to datetime object."""
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return datetime.now()


def is_premarket(dt: datetime) -> bool:
    t = dt.time()
    return dtime(4, 0) <= t < dtime(9, 30)


def is_rth(dt: datetime) -> bool:
    t = dt.time()
    return dtime(9, 30) <= t < dtime(16, 0)


def is_in_opening_range(dt: datetime, or_minutes: int = 5) -> bool:
    t = dt.time()
    or_end = (datetime.combine(dt.date(), dtime(9, 30)) +
              timedelta(minutes=or_minutes)).time()
    return dtime(9, 30) <= t < or_end


class PDPMORIndicator:
    """
    Draws PD/PM/OR levels and EMAs on a pyqtgraph plot.
    Call draw(plot_widget, candles) to render.
    Call clear(plot_widget) to remove all items.
    """

    def __init__(self, or_minutes: int = 5,
                 show_pd: bool = True,
                 show_pm: bool = True,
                 show_or: bool = True,
                 show_ema9: bool = True,
                 show_ema20: bool = True,
                 show_ema50: bool = True):
        self.or_minutes = or_minutes
        self.show_pd    = show_pd
        self.show_pm    = show_pm
        self.show_or    = show_or
        self.show_ema9  = show_ema9
        self.show_ema20 = show_ema20
        self.show_ema50 = show_ema50
        self._items     = []

    def clear(self, plot):
        for item in self._items:
            try: plot.removeItem(item)
            except: pass
        self._items.clear()

    def draw(self, plot, candles: list):
        """Main entry point — draws all levels and EMAs."""
        self.clear(plot)
        if not candles:
            return

        closes  = [c["close"] for c in candles]
        highs   = [c["high"]  for c in candles]
        lows    = [c["low"]   for c in candles]
        opens   = [c["open"]  for c in candles]
        n       = len(candles)

        # ── EMAs ─────────────────────────────────────────────────────────────
        if self.show_ema9:
            self._draw_ema(plot, closes, 9,  "#3b82f6")   # blue
        if self.show_ema20:
            self._draw_ema(plot, closes, 20, "#f97316")   # orange
        if self.show_ema50:
            self._draw_ema(plot, closes, 50, "#eab308")   # yellow

        # ── Parse sessions ────────────────────────────────────────────────────
        dts = [parse_dt(c["datetime"]) for c in candles]

        # Find day boundaries
        day_groups = {}
        for i, dt in enumerate(dts):
            day_key = dt.date()
            if day_key not in day_groups:
                day_groups[day_key] = []
            day_groups[day_key].append(i)

        sorted_days = sorted(day_groups.keys())

        pd_high = pd_low = None
        pd_high_bar = pd_low_bar = None
        pd_high_open = pd_high_close = None
        pd_low_open  = pd_low_close  = None

        for day_idx, day in enumerate(sorted_days):
            indices = day_groups[day]

            # Find RTH candles for this day
            rth_indices = [i for i in indices if is_rth(dts[i])]
            pm_indices  = [i for i in indices if is_premarket(dts[i])]
            or_indices  = [i for i in indices
                           if is_in_opening_range(dts[i], self.or_minutes)]

            # ── Previous Day Levels ───────────────────────────────────────────
            if self.show_pd and pd_high is not None and day_idx > 0:
                self._draw_pd_box(plot, n,
                                  pd_high, pd_high_bar,
                                  pd_high_open, pd_high_close,
                                  pd_low, pd_low_bar,
                                  pd_low_open, pd_low_close)

            # Update PD for next day
            if rth_indices:
                rth_highs  = highs[rth_indices[0]:rth_indices[-1]+1]
                rth_lows   = lows[rth_indices[0]:rth_indices[-1]+1]
                rth_opens  = opens[rth_indices[0]:rth_indices[-1]+1]
                rth_closes = closes[rth_indices[0]:rth_indices[-1]+1]

                max_idx_local = rth_highs.index(max(rth_highs))
                min_idx_local = rth_lows.index(min(rth_lows))

                pd_high       = max(rth_highs)
                pd_low        = min(rth_lows)
                pd_high_bar   = rth_indices[0] + max_idx_local
                pd_low_bar    = rth_indices[0] + min_idx_local
                pd_high_open  = rth_opens[max_idx_local]
                pd_high_close = rth_closes[max_idx_local]
                pd_low_open   = rth_opens[min_idx_local]
                pd_low_close  = rth_closes[min_idx_local]

            # ── Premarket Levels ──────────────────────────────────────────────
            if self.show_pm and pm_indices and rth_indices:
                pm_highs  = highs[pm_indices[0]:pm_indices[-1]+1]
                pm_lows   = lows[pm_indices[0]:pm_indices[-1]+1]
                pm_opens  = opens[pm_indices[0]:pm_indices[-1]+1]
                pm_closes = closes[pm_indices[0]:pm_indices[-1]+1]

                pm_high_local = pm_highs.index(max(pm_highs))
                pm_low_local  = pm_lows.index(min(pm_lows))

                pm_high       = max(pm_highs)
                pm_low        = min(pm_lows)
                pm_high_bar   = pm_indices[0] + pm_high_local
                pm_low_bar    = pm_indices[0] + pm_low_local
                pm_high_open  = pm_opens[pm_high_local]
                pm_high_close = pm_closes[pm_high_local]
                pm_low_open   = pm_opens[pm_low_local]
                pm_low_close  = pm_closes[pm_low_local]

                pm_end_bar = rth_indices[-1] if rth_indices else pm_indices[-1]
                self._draw_pm_box(plot, pm_end_bar,
                                  pm_high, pm_high_bar, pm_high_open, pm_high_close,
                                  pm_low,  pm_low_bar,  pm_low_open,  pm_low_close)

            # ── Opening Range ─────────────────────────────────────────────────
            if self.show_or and or_indices:
                or_high     = max(highs[i] for i in or_indices)
                or_low      = min(lows[i]  for i in or_indices)
                or_start    = or_indices[0]
                or_end_bar  = rth_indices[-1] if rth_indices else or_indices[-1]

                self._draw_or_lines(plot, or_start, or_end_bar,
                                    or_high, or_low)

    # ─────────────────────────────────────────────
    #  DRAW HELPERS
    # ─────────────────────────────────────────────

    def _add(self, plot, item):
        plot.addItem(item)
        self._items.append(item)

    def _draw_ema(self, plot, closes, period, color):
        ema = calc_ema(closes, period)
        xs  = [i for i, v in enumerate(ema) if v is not None]
        ys  = [v for v in ema if v is not None]
        if not xs:
            return
        item = pg.PlotDataItem(xs, ys,
            pen=pg.mkPen(QColor(color), width=2))
        self._add(plot, item)

        # Label at end
        if xs and ys:
            lbl = pg.TextItem(
                text=f"EMA{period}",
                color=color,
                anchor=(0, 0.5))
            lbl.setFont(QtGui.QFont("Consolas", 8))
            lbl.setPos(xs[-1] + 1, ys[-1])
            self._add(plot, lbl)

    def _draw_pd_box(self, plot, n,
                     pd_high, pd_high_bar, pd_high_open, pd_high_close,
                     pd_low,  pd_low_bar,  pd_low_open,  pd_low_close):
        """Draw PD High box (red) and PD Low box (green)."""
        end_bar = n

        # High box: wick top → max(open, close) i.e. body top
        pd_high_body = max(pd_high_open, pd_high_close)
        high_box = pg.LinearRegionItem(
            values=[pd_high_body, pd_high],
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(QColor(255, 80, 80, 40)),
            pen=pg.mkPen(QColor("#f85149"), width=1))
        self._add(plot, high_box)

        # Low box: min(open, close) → wick bottom
        pd_low_body = min(pd_low_open, pd_low_close)
        low_box = pg.LinearRegionItem(
            values=[pd_low, pd_low_body],
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(QColor(60, 185, 80, 40)),
            pen=pg.mkPen(QColor("#3fb950"), width=1))
        self._add(plot, low_box)

        # Labels
        high_lbl = pg.TextItem(
            text=f"PD High ${pd_high:.2f}",
            color="#f85149", anchor=(0, 1))
        high_lbl.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
        high_lbl.setPos(end_bar, pd_high)
        self._add(plot, high_lbl)

        low_lbl = pg.TextItem(
            text=f"PD Low ${pd_low:.2f}",
            color="#3fb950", anchor=(0, 0))
        low_lbl.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
        low_lbl.setPos(end_bar, pd_low)
        self._add(plot, low_lbl)

    def _draw_pm_box(self, plot, end_bar,
                     pm_high, pm_high_bar, pm_high_open, pm_high_close,
                     pm_low,  pm_low_bar,  pm_low_open,  pm_low_close):
        """Draw PM High box (purple) and PM Low box (blue)."""
        # High box
        pm_high_body = max(pm_high_open, pm_high_close)
        high_box = pg.LinearRegionItem(
            values=[pm_high_body, pm_high],
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(QColor(140, 80, 230, 40)),
            pen=pg.mkPen(QColor("#8957e5"), width=1))
        self._add(plot, high_box)

        # Low box
        pm_low_body = min(pm_low_open, pm_low_close)
        low_box = pg.LinearRegionItem(
            values=[pm_low, pm_low_body],
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(QColor(30, 100, 200, 40)),
            pen=pg.mkPen(QColor("#58a6ff"), width=1))
        self._add(plot, low_box)

        # Labels
        high_lbl = pg.TextItem(
            text=f"PM High ${pm_high:.2f}",
            color="#8957e5", anchor=(0, 1))
        high_lbl.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
        high_lbl.setPos(end_bar, pm_high)
        self._add(plot, high_lbl)

        low_lbl = pg.TextItem(
            text=f"PM Low ${pm_low:.2f}",
            color="#58a6ff", anchor=(0, 0))
        low_lbl.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
        low_lbl.setPos(end_bar, pm_low)
        self._add(plot, low_lbl)

    def _draw_or_lines(self, plot, or_start, or_end, or_high, or_low):
        """Draw OR High (lime) and OR Low (orange) horizontal lines."""
        # High line
        high_line = pg.PlotDataItem(
            [or_start, or_end], [or_high, or_high],
            pen=pg.mkPen(QColor(LIME), width=2))
        self._add(plot, high_line)

        # Low line
        low_line = pg.PlotDataItem(
            [or_start, or_end], [or_low, or_low],
            pen=pg.mkPen(QColor(ORANGE), width=2))
        self._add(plot, low_line)

        # Labels
        high_lbl = pg.TextItem(
            text=f"OR High ${or_high:.2f}",
            color=LIME, anchor=(0, 1))
        high_lbl.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
        high_lbl.setPos(or_end, or_high)
        self._add(plot, high_lbl)

        low_lbl = pg.TextItem(
            text=f"OR Low ${or_low:.2f}",
            color=ORANGE, anchor=(0, 0))
        low_lbl.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
        low_lbl.setPos(or_end, or_low)
        self._add(plot, low_lbl)
