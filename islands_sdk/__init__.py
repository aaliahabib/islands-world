"""islands_sdk — the tiny bridge between an island game and Islands World.

An island is just a normal pygame program. The only thing it owes the platform
is a score:

    from islands_sdk import submit_score, game_over

    submit_score(n)         # call whenever the score changes
    game_over(final_score)  # call once when a run ends

Run natively (PyCharm, terminal) these are no-ops that print to the console, so
your game runs completely unchanged on your own machine.

Run in the browser (built to WASM with pygbag, inside Islands World) they
postMessage the score up to the overworld shell, which puts it on the global
scoreboard.

You should not need to edit this file. Kids: this is platform code, leave it
alone and Claude will keep it working.
"""

from __future__ import annotations

import json
import sys

__all__ = ["submit_score", "game_over", "is_browser", "reset"]

# JS installed into the island page so ESC gets you back to the world.
#
# The island runs in an iframe and takes keyboard focus while you play, which
# means the overworld never sees your keystrokes — pressing ESC did nothing at
# all. Nothing in the game's Python can fix that, because the key never reaches
# Python either. So we listen at the page level and tell the shell to close us.
_ESCAPE_BRIDGE = """
(function () {
  if (window.__islandsEscapeBridge) return;
  window.__islandsEscapeBridge = true;
  window.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      event.preventDefault();
      parent.postMessage({ type: "exit" }, "*");
    }
  }, true);
})();
"""

# pygbag/Pyodide compile to Emscripten, which is how we know we are in a browser.
IS_BROWSER = sys.platform == "emscripten"

# The pygbag runtime injects a `platform` module exposing the JS `window`.
_window = None
if IS_BROWSER:  # pragma: no cover - only true inside the browser build
    try:
        import platform as _pygbag_platform

        _window = _pygbag_platform.window
    except Exception:
        _window = None

    if _window is not None:
        try:
            _window.eval(_ESCAPE_BRIDGE)
        except Exception:
            pass  # ESC just won't work; the on-screen back button still does

# Remember the last score we sent so a game calling submit_score() every frame
# doesn't flood the shell (and the server) with identical messages.
_last_score: int | None = None
_game_over_sent = False


def is_browser() -> bool:
    """True when this island is running inside Islands World in a browser."""
    return IS_BROWSER


def _post(payload: dict) -> None:
    """Send a message to the parent shell. Never raises — a broken bridge must
    never take down a kid's game."""
    if not IS_BROWSER or _window is None:
        return
    message = json.dumps(payload)
    try:
        # Build the object on the JS side so the shell receives a real structured
        # clone rather than a Python proxy.
        _window.parent.postMessage(_window.JSON.parse(message), "*")
    except Exception:
        try:
            _window.eval(f"parent.postMessage({message}, '*')")
        except Exception:
            pass


def _coerce_score(value) -> int | None:
    """Scores are honor-system, but they still have to be a number we can send."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    # Guard against inf/NaN sneaking through as a float and against absurd
    # values breaking JSON on the other side. This is NOT anti-cheat — it only
    # keeps the message well-formed.
    if abs(n) > 10**15:
        return None
    return n


def submit_score(value) -> None:
    """Report the player's current score. Call this whenever the score changes."""
    global _last_score

    n = _coerce_score(value)
    if n is None or n == _last_score:
        return
    _last_score = n

    if IS_BROWSER:
        _post({"type": "score", "value": n})
    else:
        print(f"[islands_sdk] score = {n}")


def game_over(value) -> None:
    """Report the final score for this run. Call once when the run ends.

    In the browser the shell shows a consistent "game over" overlay with a
    button back out to the world. Natively this just prints.
    """
    global _game_over_sent

    n = _coerce_score(value)
    if n is None:
        n = _last_score if _last_score is not None else 0
    if _game_over_sent:
        return
    _game_over_sent = True

    if IS_BROWSER:
        _post({"type": "game_over", "value": n})
    else:
        print(f"[islands_sdk] GAME OVER — final score {n}")


def reset() -> None:
    """Clear the sent-score memory so a fresh run can report from zero again.

    The template calls this when the player restarts.
    """
    global _last_score, _game_over_sent
    _last_score = None
    _game_over_sent = False
