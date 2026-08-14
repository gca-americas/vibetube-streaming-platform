import { useCallback, useEffect, useRef } from "react";

/** Maximum rotation at the corners of the element, in degrees. */
const MAX_TILT = 6.5;

/**
 * Pointer-tracked 3D tilt plus a specular highlight.
 *
 * Writes CSS custom properties rather than React state: a pointermove-driven
 * re-render of every card in the grid would be far too expensive, and these
 * values only ever feed `transform` and a gradient position.
 *
 * Returns props to spread onto the element that carries the `.tilt` class.
 */
export const useTilt = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  const frame = useRef(0);

  // pointermove fires much faster than the compositor can use, so collapse
  // bursts down to one write per frame.
  const handlePointerMove = useCallback((event: React.PointerEvent<T>) => {
    const element = ref.current;
    if (!element) return;

    const { clientX, clientY } = event;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) return;

      const x = (clientX - rect.left) / rect.width;
      const y = (clientY - rect.top) / rect.height;

      element.style.setProperty("--ry", `${(x - 0.5) * MAX_TILT * 2}deg`);
      element.style.setProperty("--rx", `${(0.5 - y) * MAX_TILT * 2}deg`);
      element.style.setProperty("--mx", `${x * 100}%`);
      element.style.setProperty("--my", `${y * 100}%`);
    });
  }, []);

  const handlePointerLeave = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    cancelAnimationFrame(frame.current);
    element.style.setProperty("--rx", "0deg");
    element.style.setProperty("--ry", "0deg");
  }, []);

  // A queued frame holds a closure over the element after unmount otherwise.
  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  return {
    ref,
    onPointerMove: handlePointerMove,
    onPointerLeave: handlePointerLeave,
  };
};
