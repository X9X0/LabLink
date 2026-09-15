/**
 * LabLink Mobile - Button Component
 */

import React from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  StyleProp,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'danger';
type ButtonSize = 'small' | 'medium' | 'large';

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
}

export const Button: React.FC<ButtonProps> = ({
  title,
  onPress,
  variant = 'primary',
  size = 'medium',
  disabled = false,
  loading = false,
  style,
  textStyle,
}) => {
  const buttonStyle: StyleProp<ViewStyle> = [
    styles.button,
    buttonVariants[variant],
    buttonSizes[size],
    disabled && styles.buttonDisabled,
    style,
  ];

  const textStyleCombined: StyleProp<TextStyle> = [
    styles.text,
    textVariants[variant],
    textSizes[size],
    disabled && styles.textDisabled,
    textStyle,
  ];

  return (
    <TouchableOpacity
      style={buttonStyle}
      onPress={onPress}
      disabled={disabled || loading}
      activeOpacity={0.7}
    >
      {loading ? (
        <ActivityIndicator
          color={variant === 'outline' ? Colors.primary : '#FFFFFF'}
        />
      ) : (
        <Text style={textStyleCombined}>{title}</Text>
      )}
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  button: {
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // Variants
  buttonPrimary: {
    backgroundColor: Colors.primary,
  },
  buttonSecondary: {
    backgroundColor: Colors.secondary,
  },
  buttonOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: Colors.primary,
  },
  buttonDanger: {
    backgroundColor: Colors.error,
  },

  // Sizes
  buttonSmall: {
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.md,
  },
  buttonMedium: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.lg,
  },
  buttonLarge: {
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.xl,
  },

  // Disabled
  buttonDisabled: {
    opacity: 0.5,
  },

  // Text styles
  text: {
    fontWeight: Typography.fontWeight.semibold,
  },
  textPrimary: {
    color: '#FFFFFF',
  },
  textSecondary: {
    color: '#FFFFFF',
  },
  textOutline: {
    color: Colors.primary,
  },
  textDanger: {
    color: '#FFFFFF',
  },
  textSmall: {
    fontSize: Typography.fontSize.sm,
  },
  textMedium: {
    fontSize: Typography.fontSize.base,
  },
  textLarge: {
    fontSize: Typography.fontSize.lg,
  },
  textDisabled: {
    opacity: 0.7,
  },
});

// Explicit maps, rather than building the style key from the variant string.
// A computed key forces TypeScript to widen the lookup to every entry in the
// sheet -- text styles included -- so the ViewStyle array picked up fontWeight
// and stopped type-checking. These also make an unknown variant a compile
// error instead of undefined at render time.
const buttonVariants: Record<ButtonVariant, ViewStyle> = {
  primary: styles.buttonPrimary,
  secondary: styles.buttonSecondary,
  outline: styles.buttonOutline,
  danger: styles.buttonDanger,
};

const buttonSizes: Record<ButtonSize, ViewStyle> = {
  small: styles.buttonSmall,
  medium: styles.buttonMedium,
  large: styles.buttonLarge,
};

const textVariants: Record<ButtonVariant, TextStyle> = {
  primary: styles.textPrimary,
  secondary: styles.textSecondary,
  outline: styles.textOutline,
  danger: styles.textDanger,
};

const textSizes: Record<ButtonSize, TextStyle> = {
  small: styles.textSmall,
  medium: styles.textMedium,
  large: styles.textLarge,
};
