/**
 * LabLink Mobile - Login Screen
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
  Image,
} from 'react-native';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Colors, Typography, Spacing } from '../constants/theme';

export const LoginScreen: React.FC = () => {
  const { login, loginWithMFA, authenticateWithBiometric, biometricAvailable, biometricEnabled } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [requiresMFA, setRequiresMFA] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string; totp?: string }>({});

  const handleBiometricLogin = async () => {
    try {
      const success = await authenticateWithBiometric();
      if (!success) {
        Alert.alert('Authentication Failed', 'Biometric authentication was not successful');
      }
      // If successful, user is automatically logged in via AuthContext
    } catch (error) {
      Alert.alert('Error', 'Failed to authenticate with biometrics');
    }
  };

  const handleLogin = async () => {
    // Validate inputs
    const newErrors: typeof errors = {};
    if (!username.trim()) {
      newErrors.username = 'Username is required';
    }
    if (!password.trim()) {
      newErrors.password = 'Password is required';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setErrors({});
    setLoading(true);

    try {
      const response = await login(username, password);

      if (response.requires_mfa) {
        setRequiresMFA(true);
      }
      // If successful and no MFA required, user is automatically set in AuthContext
    } catch (error: any) {
      Alert.alert(
        'Login Failed',
        error?.response?.data?.detail || 'Invalid username or password'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleMFALogin = async () => {
    if (!totpCode.trim()) {
      setErrors({ totp: 'Verification code is required' });
      return;
    }

    setErrors({});
    setLoading(true);

    try {
      await loginWithMFA(username, totpCode);
      // If successful, user is automatically set in AuthContext
    } catch (error: any) {
      Alert.alert(
        'Verification Failed',
        error?.response?.data?.detail || 'Invalid verification code'
      );
    } finally {
      setLoading(false);
    }
  };

  const renderLoginForm = () => (
    <>
      <Input
        label="Username"
        value={username}
        onChangeText={setUsername}
        placeholder="Enter your username"
        autoCapitalize="none"
        autoCorrect={false}
        error={errors.username}
      />

      <Input
        label="Password"
        value={password}
        onChangeText={setPassword}
        placeholder="Enter your password"
        secureTextEntry
        error={errors.password}
      />

      <Button
        title="Login"
        onPress={handleLogin}
        loading={loading}
        style={styles.loginButton}
      />

      {biometricAvailable && biometricEnabled && (
        <>
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>OR</Text>
            <View style={styles.dividerLine} />
          </View>

          <Button
            title="Login with Biometrics"
            onPress={handleBiometricLogin}
            variant="outline"
          />
        </>
      )}
    </>
  );

  const renderMFAForm = () => (
    <>
      <Text style={styles.mfaText}>
        Enter the 6-digit code from your authenticator app
      </Text>

      <Input
        label="Verification Code"
        value={totpCode}
        onChangeText={setTotpCode}
        placeholder="000000"
        keyboardType="number-pad"
        maxLength={6}
        error={errors.totp}
      />

      <Button
        title="Verify"
        onPress={handleMFALogin}
        loading={loading}
        style={styles.loginButton}
      />

      <Button
        title="Back"
        onPress={() => setRequiresMFA(false)}
        variant="outline"
      />
    </>
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.logoContainer}>
          <Text style={styles.logo}>⚡</Text>
          <Text style={styles.title}>LabLink</Text>
          <Text style={styles.subtitle}>Laboratory Equipment Control</Text>
        </View>

        <View style={styles.formContainer}>
          {requiresMFA ? renderMFAForm() : renderLoginForm()}
        </View>

        <Text style={styles.version}>v1.1.0</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.light.background,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: Spacing['2xl'],
  },
  logo: {
    fontSize: 64,
    marginBottom: Spacing.md,
  },
  title: {
    fontSize: Typography.fontSize['3xl'],
    fontWeight: Typography.fontWeight.bold,
    color: Colors.primary,
    marginBottom: Spacing.xs,
  },
  subtitle: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.textSecondary,
  },
  formContainer: {
    marginBottom: Spacing.xl,
  },
  loginButton: {
    marginBottom: Spacing.md,
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: Spacing.lg,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: Colors.light.border,
  },
  dividerText: {
    marginHorizontal: Spacing.md,
    color: Colors.light.textSecondary,
    fontSize: Typography.fontSize.sm,
  },
  mfaText: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.textSecondary,
    textAlign: 'center',
    marginBottom: Spacing.lg,
  },
  version: {
    textAlign: 'center',
    color: Colors.light.textSecondary,
    fontSize: Typography.fontSize.xs,
  },
});
