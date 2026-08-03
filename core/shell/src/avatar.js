// Stick figures: who you are in the world.
//
// A figure is three small numbers (colour, head, hat) so it costs almost
// nothing to send over the wire. Everything else — walking, waving, jumping —
// is animation computed locally from a clock, not sent.

export const COLOURS = [
  { name: "INK", value: "#000000" },
  { name: "TEAL", value: "#0a7d78" },
  { name: "ORANGE", value: "#c2560c" },
  { name: "PURPLE", value: "#6b3fa0" },
  { name: "PINK", value: "#c2185b" },
  { name: "GREEN", value: "#2e7d32" },
  { name: "BLUE", value: "#1857b8" },
  { name: "RUST", value: "#8d3b2f" },
];

export const HEADS = ["ROUND", "SQUARE", "TRIANGLE"];
export const HATS = ["NONE", "CAP", "ANTENNA", "CROWN", "SPIKES"];

export const DEFAULT_AVATAR = { c: 0, h: 0, t: 0 };

/** Clamp whatever arrived (from storage, or another player) into something drawable. */
export function sanitizeAvatar(raw) {
  const pick = (value, length) => {
    const n = Number(value);
    return Number.isInteger(n) && n >= 0 && n < length ? n : 0;
  };
  if (!raw || typeof raw !== "object") return { ...DEFAULT_AVATAR };
  return {
    c: pick(raw.c, COLOURS.length),
    h: pick(raw.h, HEADS.length),
    t: pick(raw.t, HATS.length),
  };
}

export function avatarColour(avatar) {
  return COLOURS[sanitizeAvatar(avatar).c].value;
}

// ── Emotes ─────────────────────────────────────────────────────────────────
// Each emote is a pose function of `t` (0→1 through the animation). Returning
// joint angles rather than pixels keeps the drawing code in one place.

export const EMOTES = ["WAVE", "JUMP", "DANCE", "SPIN", "SHRUG"];
export const EMOTE_DURATION = 2.2;

const TAU = Math.PI * 2;

// Limb angles are measured from STRAIGHT DOWN, in radians, positive swinging
// toward the figure's front. So 0 = hanging straight down, ±π/2 = straight out
// sideways, ±π = straight up. Keeping one convention for all four limbs is the
// whole trick — mixing conventions makes both legs land in the same place.
function basePose() {
  return {
    lean: 0,
    bob: 0,
    squash: 1,
    spin: 0,
    armBack: -0.55,
    armFront: 0.55,
    legBack: -0.25,
    legFront: 0.25,
  };
}

/** Walking is not an emote — it plays whenever you're moving. */
function walkPose(pose, phase) {
  const swing = Math.sin(phase * TAU) * 0.55;
  pose.legBack = -swing;
  pose.legFront = swing;
  // Arms counter-swing, which is what makes a walk read as a walk.
  // Kept splayed off the spine so the arms stay visible mid-stride.
  pose.armBack = -0.35 + swing;
  pose.armFront = 0.35 - swing;
  pose.bob = -Math.abs(Math.cos(phase * TAU)) * 1.8;
  return pose;
}

const EMOTE_POSES = {
  WAVE(pose, t) {
    // Front arm up and waving; the other stays down.
    pose.armFront = 2.45 + Math.sin(t * TAU * 4) * 0.35;
    pose.armBack = -0.25;
    pose.lean = 0.05;
    return pose;
  },
  JUMP(pose, t) {
    // Two hops, with a squash on landing.
    const hop = Math.abs(Math.sin(t * TAU * 2));
    pose.bob = -hop * 24;
    pose.squash = 1 - (1 - hop) * 0.12;
    pose.armFront = 2.5 * hop + 0.55 * (1 - hop);
    pose.armBack = -2.5 * hop - 0.55 * (1 - hop);
    pose.legFront = 0.22 + hop * 0.5;
    pose.legBack = -0.22 - hop * 0.5;
    return pose;
  },
  DANCE(pose, t) {
    const beat = Math.sin(t * TAU * 3);
    pose.lean = beat * 0.2;
    pose.bob = -Math.abs(beat) * 5;
    pose.armFront = 1.6 + beat * 1.1;
    pose.armBack = -1.6 + beat * 1.1;
    pose.legFront = 0.3 - beat * 0.3;
    pose.legBack = -0.3 - beat * 0.3;
    return pose;
  },
  SPIN(pose, t) {
    pose.spin = t * TAU;
    // Arms straight out, so the spin is legible.
    pose.armFront = Math.PI / 2;
    pose.armBack = -Math.PI / 2;
    return pose;
  },
  SHRUG(pose, t) {
    const up = Math.sin(Math.min(t, 0.55) / 0.55 * Math.PI) * 0.9;
    pose.armFront = 0.55 + up * 1.0;
    pose.armBack = -0.55 - up * 1.0;
    pose.bob = -up * 2;
    pose.lean = Math.sin(t * TAU) * 0.05;
    return pose;
  },
};

/**
 * Work out how a figure should be posed right now.
 * @param {object} state  { emote, emoteT (0..1), walkPhase, moving }
 */
export function poseFor(state) {
  const pose = basePose();
  if (state.emote && EMOTE_POSES[state.emote]) {
    return EMOTE_POSES[state.emote](pose, state.emoteT);
  }
  if (state.moving) return walkPose(pose, state.walkPhase);
  return pose;
}

// ── Drawing ────────────────────────────────────────────────────────────────

// Geometry, in local units with the feet at y = 0 and the figure ~46 tall.
const HEAD_R = 7;
const HEAD_Y = -39; // centre of the head
const NECK_Y = -32;
const SHOULDER_Y = -29;
const HIP_Y = -16;
const ARM_LEN = 13;
const LEG_LEN = 16;

/**
 * Draw a stick figure standing with its feet at (x, y).
 * `facing` is 1 for right, -1 for left.
 */
export function drawFigure(ctx, x, y, avatar, pose, facing = 1, scale = 1) {
  const spec = sanitizeAvatar(avatar);
  const colour = COLOURS[spec.c].value;

  ctx.save();
  ctx.translate(x, y + (pose.bob || 0) * scale);
  ctx.scale(facing * scale, scale);
  if (pose.spin) {
    // Pivot around the middle of the body, not the feet.
    ctx.translate(0, -22);
    ctx.rotate(pose.spin);
    ctx.translate(0, 22);
  }
  if (pose.lean) ctx.rotate(pose.lean);
  if (pose.squash && pose.squash !== 1) ctx.scale(1, pose.squash);

  ctx.strokeStyle = colour;
  ctx.fillStyle = colour;
  ctx.lineWidth = 2.4;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  // Spine.
  ctx.beginPath();
  ctx.moveTo(0, NECK_Y);
  ctx.lineTo(0, HIP_Y);
  ctx.stroke();

  // Limbs. Angle 0 hangs straight down; positive swings forward.
  const limb = (fromY, angle, length) => {
    ctx.beginPath();
    ctx.moveTo(0, fromY);
    ctx.lineTo(Math.sin(angle) * length, fromY + Math.cos(angle) * length);
    ctx.stroke();
  };
  limb(SHOULDER_Y, pose.armBack, ARM_LEN);
  limb(SHOULDER_Y, pose.armFront, ARM_LEN);
  limb(HIP_Y, pose.legBack, LEG_LEN);
  limb(HIP_Y, pose.legFront, LEG_LEN);

  // Head.
  ctx.beginPath();
  if (HEADS[spec.h] === "SQUARE") {
    ctx.rect(-HEAD_R, HEAD_Y - HEAD_R, HEAD_R * 2, HEAD_R * 2);
  } else if (HEADS[spec.h] === "TRIANGLE") {
    ctx.moveTo(0, HEAD_Y - HEAD_R - 1);
    ctx.lineTo(HEAD_R + 1.5, HEAD_Y + HEAD_R);
    ctx.lineTo(-HEAD_R - 1.5, HEAD_Y + HEAD_R);
    ctx.closePath();
  } else {
    ctx.arc(0, HEAD_Y, HEAD_R, 0, TAU);
  }
  ctx.stroke();

  drawHat(ctx, HATS[spec.t], HEAD_Y);
  ctx.restore();
}

function drawHat(ctx, hat, headCentreY) {
  const top = headCentreY - HEAD_R;
  ctx.beginPath();
  switch (hat) {
    case "CAP":
      ctx.moveTo(-HEAD_R - 1, top + 1);
      ctx.lineTo(HEAD_R + 1, top + 1);
      ctx.moveTo(-HEAD_R - 5, top + 1);
      ctx.lineTo(-HEAD_R - 1, top + 1);
      ctx.moveTo(-HEAD_R, top + 1);
      ctx.quadraticCurveTo(0, top - 5, HEAD_R, top + 1);
      break;
    case "ANTENNA":
      ctx.moveTo(0, top);
      ctx.lineTo(0, top - 7);
      ctx.moveTo(-2.2, top - 9);
      ctx.arc(0, top - 9, 2.2, 0, TAU);
      break;
    case "CROWN":
      ctx.moveTo(-HEAD_R, top);
      ctx.lineTo(-HEAD_R, top - 5);
      ctx.lineTo(-HEAD_R / 2, top - 2);
      ctx.lineTo(0, top - 6);
      ctx.lineTo(HEAD_R / 2, top - 2);
      ctx.lineTo(HEAD_R, top - 5);
      ctx.lineTo(HEAD_R, top);
      break;
    case "SPIKES":
      for (let i = -1; i <= 1; i++) {
        ctx.moveTo(i * 4, top + 1);
        ctx.lineTo(i * 4 + 1.5, top - 6);
      }
      break;
    default:
      ctx.closePath();
      return;
  }
  ctx.stroke();
}
