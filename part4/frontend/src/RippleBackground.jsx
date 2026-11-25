import { useEffect, useRef, useState } from "react";

const CELL = 56;

export default function RippleBackground() {
  const [grid, setGrid] = useState({ r: 0, c: 0 });
  const box = useRef(null);
  const cols = useRef(0);
  const prev = useRef(null);

  useEffect(() => {
    // Check for reduced motion
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const size = () => {
      cols.current = Math.ceil(window.innerWidth / CELL) + 1;
      setGrid({ r: Math.ceil(window.innerHeight / CELL) + 1, c: cols.current });
    };

    const move = (e) => {
      const el =
        box.current?.children[
          Math.floor(e.clientY / CELL) * cols.current +
            Math.floor(e.clientX / CELL)
        ];
      if (el === prev.current) return;

      // Remove hover from previous cell
      prev.current?.classList.remove("hover");
      // Add hover to current cell
      el?.classList.add("hover");
      prev.current = el || null;
    };

    const leave = () => {
      prev.current?.classList.remove("hover");
      prev.current = null;
    };

    size();
    window.addEventListener("resize", size);
    window.addEventListener("pointermove", move);
    document.documentElement.addEventListener("mouseleave", leave);

    return () => {
      window.removeEventListener("resize", size);
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("mouseleave", leave);
    };
  }, []);

  return (
    <div
      ref={box}
      className="ripple"
      aria-hidden="true"
      style={{
        gridTemplateColumns: `repeat(${grid.c}, ${CELL}px)`,
        gridTemplateRows: `repeat(${grid.r}, ${CELL}px)`,
      }}
    >
      {Array.from({ length: grid.r * grid.c }, (_, i) => (
        <div key={i} className="cell" />
      ))}
    </div>
  );
}
