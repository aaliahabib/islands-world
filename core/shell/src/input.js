// Keyboard state for the overworld. Deliberately tiny.

import { EMOTES } from "./config.js";

const MOVEMENT = {
  KeyW: "up",
  ArrowUp: "up",
  KeyS: "down",
  ArrowDown: "down",
  KeyA: "left",
  ArrowLeft: "left",
  KeyD: "right",
  ArrowRight: "right",
};

export class Input {
  constructor({ onEnter, onExit, onEmote }) {
    this.state = { up: false, down: false, left: false, right: false };
    this.enabled = true;

    this.onKeyDown = (event) => {
      if (event.target instanceof HTMLInputElement) return;

      if (event.code === "Escape") {
        onExit();
        return;
      }
      if (!this.enabled) return;

      const direction = MOVEMENT[event.code];
      if (direction) {
        this.state[direction] = true;
        event.preventDefault();
        return;
      }
      if (event.code === "KeyE" || event.code === "Enter" || event.code === "Space") {
        event.preventDefault();
        onEnter();
        return;
      }
      const emoteIndex = "Digit1 Digit2 Digit3 Digit4 Digit5".split(" ").indexOf(event.code);
      if (emoteIndex >= 0 && EMOTES[emoteIndex]) {
        onEmote(EMOTES[emoteIndex]);
      }
    };

    this.onKeyUp = (event) => {
      const direction = MOVEMENT[event.code];
      if (direction) this.state[direction] = false;
    };

    // Releasing keys when the window loses focus stops the "stuck running"
    // bug you get from alt-tabbing mid-stride.
    this.onBlur = () => this.releaseAll();

    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
    window.addEventListener("blur", this.onBlur);
  }

  releaseAll() {
    for (const key of Object.keys(this.state)) this.state[key] = false;
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    if (!enabled) this.releaseAll();
  }

  destroy() {
    window.removeEventListener("keydown", this.onKeyDown);
    window.removeEventListener("keyup", this.onKeyUp);
    window.removeEventListener("blur", this.onBlur);
  }
}
