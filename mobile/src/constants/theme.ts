/**
 * LabLink Mobile - Theme
 * Colors, typography, and spacing constants
 */

export const Colors = {
  // Primary brand colors
  primary: '#3B82F6', // Blue
  primaryDark: '#2563EB',
  primaryLight: '#60A5FA',

  // Secondary colors
  secondary: '#8B5CF6', // Purple
  secondaryDark: '#7C3AED',
  secondaryLight: '#A78BFA',

  // Status colors
  success: '#10B981', // Green
  warning: '#F59E0B', // Orange
  error: '#EF4444', // Red
  info: '#3B82F6', // Blue

  // Alarm severity colors
  alarmCritical: '#DC2626',
  alarmError: '#EF4444',
  alarmWarning: '#F59E0B',
  alarmInfo: '#3B82F6',

  // Equipment status colors
  connected: '#10B981',
  disconnected: '#6B7280',
  equipmentError: '#EF4444',

  // Light theme
  light: {
    background: '#FFFFFF',
    surface: '#F9FAFB',
    text: '#111827',
    textSecondary: '#6B7280',
    border: '#E5E7EB',
    disabled: '#D1D5DB',
  },

  // Dark theme
  dark: {
    background: '#111827',
    surface: '#1F2937',
    text: '#F9FAFB',
    textSecondary: '#9CA3AF',
    border: '#374151',
    disabled: '#4B5563',
  },
};

export const Typography = {
  // Font sizes
  fontSize: {
    xs: 12,
    sm: 14,
    base: 16,
    lg: 18,
    xl: 20,
    '2xl': 24,
    '3xl': 30,
    '4xl': 36,
  },

  // Font weights
  fontWeight: {
    normal: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
  },

  // Line heights
  lineHeight: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
  },
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  '2xl': 48,
  '3xl': 64,
};

export const BorderRadius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  full: 9999,
};

export const Shadows = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  lg: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
  },
};
