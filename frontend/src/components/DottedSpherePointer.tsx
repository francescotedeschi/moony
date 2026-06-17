import type { CSSProperties, RefObject } from "react";

export const DOTTED_POINTER_R = 63;

export type DragMotion = {
  vx: number;
  vy: number;
  active: boolean;
};

type Props = {
  padOffset?: { x: number; y: number };
  colorDiscR?: number;
  dragMotionRef?: RefObject<DragMotion>;
  hovered?: boolean;
  className?: string;
  style?: CSSProperties;
};

export function DottedSpherePointer({
  hovered = false,
  className,
  style,
}: Props) {
  return (
    <div
      data-testid="dotted-pointer-tracker"
      className={`moony-glass-pointer-ring${hovered ? " moony-glass-pointer-ring--hovered" : ""}${
        className ? ` ${className}` : ""
      }`}
      style={style}
      aria-hidden
    />
  );
}
