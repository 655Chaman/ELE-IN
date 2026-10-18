import React from 'react';
import { cn } from '@/lib/utils';

export interface ElesiumLogoProps {
  className?: string;
  imgClassName?: string;
  size?: number | string;
  variant?: 'auto' | 'white' | 'dark' | 'full';
  showBadge?: boolean;
  alt?: string;
}

export const ElesiumLogo: React.FC<ElesiumLogoProps> = ({
  className,
  imgClassName,
  size = 16,
  variant = 'auto',
  showBadge = false,
  alt = 'Elesium AI',
}) => {
  const dimension = typeof size === 'number' ? `${size}px` : size;
  const style = size ? { width: dimension, height: dimension, minWidth: dimension, minHeight: dimension } : undefined;

  const renderImg = () => {
    const commonProps = {
      alt,
      style,
      draggable: false,
      loading: "eager" as const,
      decoding: "async" as const,
    };

    if (variant === 'full') {
      return (
        <img
          src="/elesium-logo.png?v=3"
          {...commonProps}
          className={cn("aspect-square object-contain shrink-0 block", imgClassName)}
        />
      );
    }

    if (variant === 'white') {
      return (
        <img
          src="/elesium-white.png?v=3"
          {...commonProps}
          className={cn("aspect-square object-contain shrink-0 block", imgClassName)}
        />
      );
    }

    if (variant === 'dark') {
      return (
        <img
          src="/elesium-dark.png?v=3"
          {...commonProps}
          className={cn("aspect-square object-contain shrink-0 block", imgClassName)}
        />
      );
    }

    return (
      <>
        {/* Light mode: crisp dark charcoal emblem */}
        <img
          src="/elesium-dark.png?v=3"
          {...commonProps}
          className={cn("aspect-square object-contain shrink-0 block dark:hidden", imgClassName)}
        />
        {/* Dark mode: crisp white emblem */}
        <img
          src="/elesium-white.png?v=3"
          {...commonProps}
          className={cn("aspect-square object-contain shrink-0 hidden dark:block", imgClassName)}
        />
      </>
    );
  };

  return (
    <span
      style={!showBadge ? style : undefined}
      className={cn(
        "inline-flex items-center select-none shrink-0",
        showBadge ? "gap-1.5 align-middle" : "justify-center aspect-square",
        className
      )}
    >
      {renderImg()}
      {showBadge && (
        <span className="text-xs font-bold text-foreground tracking-tight">
          Elesium
        </span>
      )}
    </span>
  );
};

export default ElesiumLogo;
