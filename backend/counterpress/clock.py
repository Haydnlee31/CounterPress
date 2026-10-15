"""Explicitly advanced virtual clock: no sleeping, threads or wall-clock dependence."""

from fractions import Fraction

from counterpress.domain.models import MatchTime


def positive_fraction(value: int | float | Fraction, *, allow_zero: bool = False) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("time and speed must be finite numbers")
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("time and speed must be finite numbers") from exc
    if number < 0 or (not allow_zero and number == 0):
        raise ValueError("value must be positive" if not allow_zero else "elapsed time cannot be negative")
    return number


class VirtualClock:
    """One-period replay. A multi-period clock needs explicit period-duration mapping."""

    def __init__(self, start: MatchTime, end: MatchTime, speed: float = 1):
        if start.period != end.period or start.key() > end.key():
            raise ValueError("clock requires ordered endpoints in one period")
        self.start = start
        self.end = end
        self._position_ms = Fraction(start.elapsed_ms)
        self._speed = positive_fraction(speed)
        self._playing = False

    @property
    def now(self) -> MatchTime:
        return MatchTime(period=self.start.period, elapsed_ms=int(self._position_ms))

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def speed(self) -> Fraction:
        return self._speed

    def set_speed(self, speed: float) -> None:
        self._speed = positive_fraction(speed)

    def play(self) -> None:
        self._playing = self._position_ms < self.end.elapsed_ms

    def pause(self) -> None:
        self._playing = False

    def reset(self) -> None:
        self._position_ms = Fraction(self.start.elapsed_ms)
        self._playing = False

    def advance(self, elapsed_seconds: int | float | Fraction) -> MatchTime:
        elapsed = positive_fraction(elapsed_seconds, allow_zero=True)
        if self._playing:
            self._position_ms = min(Fraction(self.end.elapsed_ms), self._position_ms + elapsed * 1000 * self._speed)
            if self._position_ms == self.end.elapsed_ms:
                self._playing = False
        return self.now
