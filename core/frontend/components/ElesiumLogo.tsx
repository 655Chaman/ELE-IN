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
  const style = size ? { width: dimension, height: dimension } : undefined;

  const renderImg = () => {
    if (variant === 'full') {
      return (
        <img
          src="/elesium-logo.png"
          alt={alt}
          style={style}
          className={cn("object-contain shrink-0", imgClassName)}
        />
      );
    }

    if (variant === 'white') {
      return (
        <img
          src="/elesium-white.png"
          alt={alt}
          style={style}
          className={cn("object-contain shrink-0", imgClassName)}
        />
      );
    }

    if (variant === 'dark') {
      return (
        <img
          src="/elesium-dark.png"
          alt={alt}
          style={style}
          className={cn("object-contain shrink-0", imgClassName)}
        />
      );
    }

    return (
      <>
        {/* Light mode: crisp dark charcoal emblem */}
        <img
          src="/elesium-dark.png"
          alt={alt}
          style={style}
          className={cn("object-contain shrink-0 dark:hidden", imgClassName)}
        />
        {/* Dark mode: crisp white emblem */}
        <img
          src="/elesium-white.png"
          alt={alt}
          style={style}
          className={cn("object-contain shrink-0 hidden dark:inline-block", imgClassName)}
        />
      </>
    );
  };

  return (
    <span className={cn("inline-flex items-center gap-1.5 align-middle select-none shrink-0", className)}>
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
