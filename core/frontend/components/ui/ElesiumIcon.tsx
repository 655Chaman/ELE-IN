import React from 'react';
import { ElesiumLogo, type ElesiumLogoProps } from '../ElesiumLogo';

export type ElesiumIconProps = ElesiumLogoProps;

export const ElesiumIcon: React.FC<ElesiumLogoProps> = (props) => {
  return <ElesiumLogo {...props} />;
};

export default ElesiumIcon;
