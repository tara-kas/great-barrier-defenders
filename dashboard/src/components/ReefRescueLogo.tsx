import React from 'react';

interface ReefRescueLogoProps {
  className?: string;
  size?: number;
}

/**
 * Official Reef Rescue Logo — matches the uploaded dual-branching coral emblem:
 * - Dark oceanic circular badge (#0B191E fill, #35525C border ring)
 * - Left stylized Y-branching coral in vibrant mint-emerald (#72E5BE)
 * - Right mirrored Y-branching coral in crisp reef white (#F8FAFC)
 */
export const ReefRescueLogo: React.FC<ReefRescueLogoProps> = ({
  className = 'w-11 h-11',
  size,
}) => {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="Reef Rescue Logo"
    >
      {/* Outer Dark Oceanic Circle & Subtle Teal Ring */}
      <circle
        cx="50"
        cy="50"
        r="46"
        fill="#0B191E"
        stroke="#35525C"
        strokeWidth="3"
      />

      {/* Left Mint-Emerald Branching Coral (#72E5BE) */}
      <g
        fill="none"
        stroke="#72E5BE"
        strokeWidth="6.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* Main trunk rising from bottom, bending right, then straight up */}
        <path d="M 38.5 79 L 38.5 53.5 L 44.8 46.5 L 44.8 34.5" />
        {/* Left side branch splitting off, bending left, then straight up */}
        <path d="M 38.5 64.5 L 28.8 54.5 L 28.8 37" />
      </g>

      {/* Right Crisp White Mirrored Branching Coral (#F8FAFC) */}
      <g
        fill="none"
        stroke="#F8FAFC"
        strokeWidth="6.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* Main trunk rising from bottom, bending left, then straight up */}
        <path d="M 62.5 79 L 62.5 53.5 L 56.2 46.5 L 56.2 34.5" />
        {/* Right side branch splitting off, bending right, then straight up */}
        <path d="M 62.5 64.5 L 72.2 54.5 L 72.2 37" />
      </g>
    </svg>
  );
};
