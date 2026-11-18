"""`OscalDateTime`: a ``datetime`` that keeps every fraction digit of the text.

OSCAL bases its datetime types on ``xs:dateTime``, whose fractional seconds
have arbitrary precision, and the schema pattern allows any number of fraction
digits. Python's ``datetime`` holds microseconds, so a plain ``datetime`` loses
the seventh digit of ``2024-01-02T03:04:05.1234567Z`` and names another instant
(issue #19). `OscalDateTime` is a ``datetime`` subclass, so ``isinstance(x,
datetime)`` holds and code that reads a field as a ``datetime`` keeps working.
It adds the digits that the text wrote, and a serialization writes them again.

This module imports only the standard library, so that ``_datatypes`` and
``models`` can import it without a cycle.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, tzinfo
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from typing import Self

__all__ = ["OscalDateTime"]

#: The digits after the decimal point of the seconds in an ISO 8601 text.
_FRACTION: Final = re.compile(r"(?<=T\d\d:\d\d:\d\d)\.(\d+)")
#: A zone designator at the end of an ISO 8601 text.
_ZONE: Final = re.compile(r"(?:Z|[+-]\d\d:\d\d(?::\d\d(?:\.\d+)?)?)$")


#: The digits of a microsecond.
_MICRO_DIGITS: Final = 6
#: The number of positional arguments of ``replace`` that reach ``microsecond``.
_MICROSECOND_ARGUMENT: Final = 7


def _default_fraction(microsecond: int) -> str:
    """Return the fraction digits that a ``datetime`` of this microsecond writes."""
    return f"{microsecond:06d}" if microsecond else ""


class OscalDateTime(datetime):
    """A ``datetime`` with a timezone that keeps every fraction digit of its text.

    ``datetime`` stores microseconds only. A value that was parsed from
    ``2024-01-02T03:04:05.1234567Z`` has ``microsecond == 123456`` and keeps
    the full digits in `fraction`. `isoformat`, `to_string`, and the JSON
    serialization of a model write them again. A value that is constructed in
    Python, with no `fraction`, writes its microseconds as a ``datetime`` does.

    **Equality and order.** Two values are equal when they name the same
    instant, with every digit counted: ``.1234567`` and ``.1234568`` differ, and
    ``.120`` and ``.12`` are equal. The same holds in a comparison with a plain
    ``datetime``, which counts as having no digits beyond the microsecond. The
    hash agrees with equality.

    **Arithmetic and precision.** Only the standard library's microsecond
    methods are limited to microseconds:

    - ``value + timedelta`` and ``value - timedelta`` keep the digits beyond the
      sixth, because a ``timedelta`` has no finer part to change them.
    - ``replace`` and ``astimezone`` keep the digits, unless ``replace`` sets
      ``microsecond``.
    - ``value - other`` gives a ``timedelta``, which holds microseconds. The
      digits beyond the sixth of both operands are **not** in the difference, so
      the difference of two values that differ only after the sixth digit is
      zero, while ``value == other`` is false. Compare values with ``<``, ``==``
      and ``>``, not by a difference, when digits beyond the sixth matter.
    - ``timestamp()``, ``strftime()``, ``timetuple()``, ``time()``,
      ``timetz()``, and ``isoformat(timespec=...)`` with a ``timespec`` other
      than ``"auto"`` use the microsecond value only and drop the digits beyond
      the sixth.
    - ``fromisoformat`` keeps the digits of the text. ``combine``,
      ``fromtimestamp``, ``now``, and the other constructors have no text to
      keep them from.

    A value is immutable and can be pickled and copied.
    """

    __slots__ = ("_fraction",)

    _fraction: str

    def __new__(  # noqa: PLR0913, PLR0917 -- the signature of ``datetime``
        cls,
        year: int,
        month: int | None = None,
        day: int | None = None,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tzinfo: tzinfo | None = None,
        *,
        fold: int = 0,
        fraction: str | None = None,
    ) -> Self:
        """Build a value like ``datetime``, with the digits of ``fraction``.

        ``fraction`` is the text after the decimal point of the seconds, with at
        least the digits of ``microsecond`` as its first six (padded with
        zeros). It is empty for a whole second. Omit it to write the
        microseconds as ``datetime`` does.

        Raises:
            ValueError: If ``fraction`` is not a run of digits, or its first
                six digits are not ``microsecond``.
        """
        self = super().__new__(
            cls,
            year,
            month,  # type: ignore[arg-type]
            day,  # type: ignore[arg-type]
            hour,
            minute,
            second,
            microsecond,
            tzinfo,
            fold=fold,  # type: ignore[arg-type]
        )
        if fraction is None:
            fraction = _default_fraction(self.microsecond)
        elif not (fraction == "" or (fraction.isascii() and fraction.isdigit())):
            msg = f"fraction must be a run of digits, got {fraction!r}"
            raise ValueError(msg)
        elif (
            int(fraction[:_MICRO_DIGITS].ljust(_MICRO_DIGITS, "0")) != self.microsecond
        ):
            msg = (
                f"fraction {fraction!r} does not start with "
                f"microsecond {self.microsecond}"
            )
            raise ValueError(msg)
        self._fraction = fraction
        return self

    # -- the digits -------------------------------------------------------------

    @property
    def fraction(self) -> str:
        """The digits after the decimal point of the seconds, as the text wrote them.

        An empty string for a whole second. At least the six digits of
        `microsecond` when a ``datetime`` was converted, and every digit of the
        text when the value was parsed: ``"1234567"`` for ``...05.1234567Z``.
        """
        return self._fraction

    @property
    def _extra(self) -> Fraction:
        """The part of the second beyond the microsecond, in microseconds."""
        rest = self._fraction[_MICRO_DIGITS:]
        return Fraction(int(rest), 10 ** len(rest)) if rest.strip("0") else Fraction(0)

    @classmethod
    def from_datetime(cls, value: datetime, fraction: str | None = None) -> Self:
        """Return the value of a ``datetime``, with ``fraction`` digits if given.

        An `OscalDateTime` keeps its own digits when ``fraction`` is omitted.
        """
        if fraction is None and isinstance(value, OscalDateTime):
            fraction = value.fraction
        return cls(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            value.tzinfo,
            fold=value.fold,
            fraction=fraction,
        )

    @classmethod
    def fromisoformat(cls, date_string: str) -> Self:
        """Parse an ISO 8601 text and keep every digit after the decimal point.

        The text must be one that ``datetime.fromisoformat`` accepts, except that
        it may have more than six fraction digits.
        """
        match = _FRACTION.search(date_string)
        if match is None:
            return super().fromisoformat(date_string)
        digits = match.group(1)
        shortened = (
            date_string[: match.start(1)]
            + digits[:_MICRO_DIGITS]
            + date_string[match.end(1) :]
        )
        parsed = super().fromisoformat(shortened)
        return cls.from_datetime(parsed, digits)

    # -- text -------------------------------------------------------------------

    def isoformat(self, sep: str = "T", timespec: str = "auto") -> str:  # type: ignore[override]
        """Return the ISO 8601 text, with every fraction digit for ``timespec="auto"``.

        Another ``timespec`` rounds down to that precision as ``datetime`` does,
        from the microsecond value.
        """
        if timespec != "auto" or self._fraction == _default_fraction(self.microsecond):
            return super().isoformat(sep, timespec)
        whole = super().isoformat(sep, "seconds")
        zone = _ZONE.search(whole)
        split = zone.start() if zone else len(whole)
        point = "." + self._fraction if self._fraction else ""
        return whole[:split] + point + whole[split:]

    def to_string(self) -> str:
        """Return the OSCAL ``date-time-with-timezone`` text of this value.

        It is `isoformat` with ``Z`` for a zero offset, which is what the JSON
        serialization of a model writes.
        """
        text = self.isoformat()
        return text[:-6] + "Z" if text.endswith("+00:00") else text

    def __repr__(self) -> str:
        base = super().__repr__()
        if self._fraction == _default_fraction(self.microsecond):
            return base
        return f"{base[:-1]}, fraction={self._fraction!r})"

    # -- equality and order -----------------------------------------------------

    def _extra_of(self, other: Any) -> Fraction:
        return other._extra if isinstance(other, OscalDateTime) else Fraction(0)  # noqa: SLF001

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, datetime):
            return NotImplemented
        return datetime.__eq__(self, other) and self._extra == self._extra_of(other)

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __lt__(self, other: datetime) -> bool:  # type: ignore[override]
        if not isinstance(other, datetime):
            return NotImplemented
        if datetime.__eq__(self, other):
            return self._extra < self._extra_of(other)
        return datetime.__lt__(self, other)

    def __le__(self, other: datetime) -> bool:  # type: ignore[override]
        if not isinstance(other, datetime):
            return NotImplemented
        if datetime.__eq__(self, other):
            return self._extra <= self._extra_of(other)
        return datetime.__lt__(self, other)

    def __gt__(self, other: datetime) -> bool:  # type: ignore[override]
        if not isinstance(other, datetime):
            return NotImplemented
        if datetime.__eq__(self, other):
            return self._extra > self._extra_of(other)
        return datetime.__gt__(self, other)

    def __ge__(self, other: datetime) -> bool:  # type: ignore[override]
        if not isinstance(other, datetime):
            return NotImplemented
        if datetime.__eq__(self, other):
            return self._extra >= self._extra_of(other)
        return datetime.__gt__(self, other)

    def __hash__(self) -> int:
        extra = self._extra
        base = datetime.__hash__(self)
        return base if not extra else hash((base, extra))

    # -- arithmetic and copies ----------------------------------------------------

    def _carry(self, result: Any) -> Any:
        """Give ``result`` the digits beyond the sixth of this value."""
        if isinstance(result, OscalDateTime) and len(self._fraction) > _MICRO_DIGITS:
            result._fraction = (  # noqa: SLF001
                f"{result.microsecond:06d}" + self._fraction[_MICRO_DIGITS:]
            )
        return result

    def __add__(self, other: timedelta) -> Self:  # type: ignore[override]
        return self._carry(datetime.__add__(self, other))

    __radd__ = __add__

    def __sub__(self, other: Any) -> Any:
        return self._carry(datetime.__sub__(self, other))

    def replace(self, *args: Any, **kwargs: Any) -> Self:  # type: ignore[override]
        """Return a copy with fields changed.

        The digits stay unless ``microsecond`` is set.
        """
        result = super().replace(*args, **kwargs)
        if "microsecond" not in kwargs and len(args) < _MICROSECOND_ARGUMENT:
            result._fraction = self._fraction  # noqa: SLF001
        return result

    __replace__ = replace

    def astimezone(self, tz: tzinfo | None = None) -> Self:  # type: ignore[override]
        """Return the value in another timezone; the digits stay."""
        result = super().astimezone(tz)
        result._fraction = self._fraction  # noqa: SLF001
        return result

    def __reduce_ex__(self, protocol: Any) -> Any:
        return (_rebuild, (type(self), self.isoformat(), self.tzinfo, self.fold))

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        return self


def _rebuild(
    cls: type[OscalDateTime], text: str, tz: tzinfo | None, fold: int
) -> OscalDateTime:
    """Rebuild a pickled or copied value from its text and its ``tzinfo``."""
    parsed = cls.fromisoformat(text)
    return parsed.replace(tzinfo=tz, fold=fold) if tz is not None else parsed
