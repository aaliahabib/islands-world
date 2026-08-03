// The DOM layer floating over the map: scoreboard, connection pill, the
// "press E" prompt, and the emote buttons.

import { EMOTES } from "./avatar.js";

const CONNECTION_LABEL = {
  online: "CONNECTED",
  connecting: "CONNECTING…",
  reconnecting: "RECONNECTING…",
  offline: "PLAYING OFFLINE",
};

export class Hud {
  constructor(elements, { onEmote }) {
    this.connectionEl = elements.connection;
    this.scoresEl = elements.scores;
    this.worldTotalEl = elements.worldTotal;
    this.promptEl = elements.prompt;
    this.emotesEl = elements.emotes;
    this.worldNameEl = elements.worldName;

    this.handle = null;
    this.promptText = null;

    for (const emote of EMOTES) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = emote;
      button.title = `Emote: ${emote}`;
      button.addEventListener("click", () => {
        onEmote(emote);
        button.blur(); // keep keyboard focus on the map
      });
      this.emotesEl.append(button);
    }

    this.setBoard([], 0);
  }

  setWorldName(name) {
    this.worldNameEl.textContent = name;
  }

  setHandle(handle) {
    this.handle = handle;
  }

  setConnection(state) {
    this.connectionEl.dataset.state = state === "reconnecting" ? "connecting" : state;
    this.connectionEl.textContent = CONNECTION_LABEL[state] || state.toUpperCase();
  }

  setPrompt(text) {
    if (text === this.promptText) return;
    this.promptText = text;
    if (!text) {
      this.promptEl.hidden = true;
      this.promptEl.textContent = "";
      return;
    }
    this.promptEl.textContent = text;
    this.promptEl.hidden = false;
  }

  setBoard(entries, worldTotal) {
    this.scoresEl.replaceChildren();

    if (!entries.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "no scores yet";
      this.scoresEl.append(li);
    }

    for (const entry of entries.slice(0, 12)) {
      const li = document.createElement("li");
      if (entry.handle === this.handle) li.classList.add("me");

      const who = document.createElement("span");
      who.className = "who";
      who.textContent = entry.handle;

      const num = document.createElement("span");
      num.className = "num";
      num.textContent = Number(entry.total || 0).toLocaleString();

      li.append(who, num);
      this.scoresEl.append(li);
    }

    this.worldTotalEl.replaceChildren();
    const label = document.createElement("span");
    label.textContent = "WORLD TOTAL";
    const value = document.createElement("span");
    value.textContent = Number(worldTotal || 0).toLocaleString();
    this.worldTotalEl.append(label, value);
  }
}
