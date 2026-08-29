export const primaryNavTargets = ["why", "proof", "how", "model"];

export function moveStage(current, direction, stageCount) {
  return Math.max(0, Math.min(stageCount - 1, current + direction));
}
