import unittest
from datetime import datetime, timedelta, timezone

from pipslayer.data.candles import Candle
from pipslayer.strategies.msnr.swings import detect_swings


class SwingDetectorTests(unittest.TestCase):
    def make_candles(self, highs, lows):
        start = datetime(2026, 5, 1, tzinfo=timezone.utc)
        return tuple(
            Candle(
                symbol="XAUUSD",
                timeframe="M15",
                timestamp=start + timedelta(minutes=15 * i),
                open=(high + low) / 2,
                high=high,
                low=low,
                close=(high + low) / 2,
                volume=1.0,
                source="test",
            )
            for i, (high, low) in enumerate(zip(highs, lows))
        )

    def test_detects_confirmed_high(self):
        candles = self.make_candles(
            [101, 102, 105, 102, 101],
            [99, 99, 99, 99, 99],
        )
        highs = [s for s in detect_swings(candles) if s.kind == "high"]
        self.assertEqual(len(highs), 1)
        self.assertEqual(highs[0].candle_index, 2)
        self.assertEqual(highs[0].confirmation_index, 4)

    def test_detects_confirmed_low(self):
        candles = self.make_candles(
            [110, 110, 110, 110, 110],
            [105, 104, 101, 104, 105],
        )
        lows = [s for s in detect_swings(candles) if s.kind == "low"]
        self.assertEqual(len(lows), 1)
        self.assertEqual(lows[0].candle_index, 2)

    def test_does_not_report_unconfirmed_end_swing(self):
        candles = self.make_candles(
            [101, 102, 103, 110],
            [99, 100, 101, 105],
        )
        self.assertEqual(detect_swings(candles), ())

    def test_rejects_invalid_bar_parameters(self):
        candles = self.make_candles([101, 102, 103], [99, 99, 99])
        with self.assertRaises(ValueError):
            detect_swings(candles, left_bars=0)
        with self.assertRaises(ValueError):
            detect_swings(candles, right_bars=0)

    def test_rejects_unordered_candles(self):
        candles = list(self.make_candles([101, 102, 103], [99, 99, 99]))
        candles[1] = Candle(
            symbol=candles[1].symbol,
            timeframe=candles[1].timeframe,
            timestamp=candles[0].timestamp,
            open=candles[1].open,
            high=candles[1].high,
            low=candles[1].low,
            close=candles[1].close,
            volume=candles[1].volume,
            source=candles[1].source,
        )
        with self.assertRaisesRegex(ValueError, "increasing timestamp"):
            detect_swings(candles)


if __name__ == "__main__":
    unittest.main()
