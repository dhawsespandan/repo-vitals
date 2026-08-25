import type { CSSProperties, ReactNode } from "react";

/**
 * The system's signature frame: a hairline box with drafting registration
 * marks at each corner. The four `<i class="corner">` elements are positioned
 * outside the border by the stylesheet, which is why they cannot be drawn with
 * a pseudo-element on the wrapper itself.
 */
export function BlueprintCorners() {
  return (
    <>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
    </>
  );
}

interface BlueprintProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  onClick?: () => void;
}

export function Blueprint({
  children,
  className = "",
  style,
  onClick,
}: BlueprintProps) {
  return (
    <div className={`blueprint ${className}`.trim()} style={style} onClick={onClick}>
      <BlueprintCorners />
      {children}
    </div>
  );
}
