import React, {type ReactNode} from 'react';
import clsx from 'clsx';
import useIsBrowser from '@docusaurus/useIsBrowser';
import {translate} from '@docusaurus/Translate';
import IconLightMode from '@theme/Icon/LightMode';
import IconDarkMode from '@theme/Icon/DarkMode';
import type {Props} from '@theme/ColorModeToggle';
import type {ColorMode} from '@docusaurus/theme-common';

import styles from './styles.module.css';

// Force binary toggle regardless of config — never expose 'system' as a state.
function getNextColorMode(colorMode: ColorMode | null) {
  return colorMode === 'dark' ? 'light' : 'dark';
}

function getColorModeLabel(colorMode: ColorMode | null): string {
  if (colorMode === 'dark') {
    return translate({
      message: 'dark mode',
      id: 'theme.colorToggle.ariaLabel.mode.dark',
      description: 'The name for the dark color mode',
    });
  }
  return translate({
    message: 'light mode',
    id: 'theme.colorToggle.ariaLabel.mode.light',
    description: 'The name for the light color mode',
  });
}

function getColorModeAriaLabel(colorMode: ColorMode | null) {
  return translate(
    {
      message: 'Switch between dark and light mode (currently {mode})',
      id: 'theme.colorToggle.ariaLabel',
      description: 'The ARIA label for the color mode toggle',
    },
    {
      mode: getColorModeLabel(colorMode),
    },
  );
}

function CurrentColorModeIcon(): ReactNode {
  // Both icons rendered; CSS shows the active one based on data-theme.
  return (
    <>
      <IconLightMode
        aria-hidden
        className={clsx(styles.toggleIcon, styles.lightToggleIcon)}
      />
      <IconDarkMode
        aria-hidden
        className={clsx(styles.toggleIcon, styles.darkToggleIcon)}
      />
    </>
  );
}

function ColorModeToggle({
  className,
  buttonClassName,
  value,
  onChange,
}: Props): ReactNode {
  const isBrowser = useIsBrowser();
  return (
    <div className={clsx(styles.toggle, className)}>
      <button
        className={clsx(
          'clean-btn',
          styles.toggleButton,
          !isBrowser && styles.toggleButtonDisabled,
          buttonClassName,
        )}
        type="button"
        onClick={() => onChange(getNextColorMode(value))}
        disabled={!isBrowser}
        title={getColorModeLabel(value)}
        aria-label={getColorModeAriaLabel(value)}

        // For accessibility decisions
        // See https://github.com/facebook/docusaurus/issues/7667#issuecomment-2724401796

        // aria-live disabled on purpose - This is annoying because:
        // - without this attribute, VoiceOver doesn't announce on button enter
        // - with this attribute, VoiceOver announces twice on ctrl+opt+space
        // - with this attribute, NVDA announces many times
        // aria-live="polite"
      >
        <CurrentColorModeIcon />
      </button>
    </div>
  );
}

export default React.memo(ColorModeToggle);
