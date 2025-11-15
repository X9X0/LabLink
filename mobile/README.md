# LabLink Mobile

**Version:** 1.1.0
**Platform:** iOS & Android
**Framework:** React Native (Expo)

A mobile application for remote control and monitoring of laboratory equipment through LabLink server.

## Features

### Authentication ✓
- Username/password login
- Multi-factor authentication (TOTP)
- Biometric authentication (Face ID / Touch ID)
- Automatic token refresh
- Secure token storage (Keychain/KeyStore)

### Equipment Management ✓
- List all connected equipment
- Real-time status updates via WebSocket
- Equipment details view
- Connect/disconnect equipment
- Send SCPI commands
- Query equipment and view responses

### Alarms & Monitoring ✓
- View all alarms with filtering (all/active/new)
- Real-time alarm notifications via WebSocket
- Acknowledge alarms
- Color-coded severity levels (critical, error, warning, info)
- Equipment-specific alarm tracking

### Settings ✓
- User profile management
- Biometric authentication toggle
- Configurable server URL
- WebSocket URL configuration
- App version and build information

### Real-Time Updates ✓
- WebSocket integration with mobile-optimized reconnection
- Automatic reconnection on network restore
- App state awareness (foreground/background)
- Exponential backoff strategy

## Technology Stack

- **Framework:** React Native with Expo
- **Language:** TypeScript
- **Navigation:** React Navigation (Stack + Tabs)
- **HTTP Client:** Axios
- **WebSocket:** Native WebSocket API
- **Secure Storage:** expo-secure-store
- **Biometric Auth:** expo-local-authentication
- **Network Detection:** @react-native-community/netinfo

## Prerequisites

- Node.js 18+ and npm
- Expo CLI
- For iOS: macOS with Xcode (for building)
- For Android: Android Studio with SDK

## Installation

### 1. Install Dependencies

```bash
cd mobile
npm install
```

### 2. Configure Server URL

Edit `src/constants/config.ts` to set your default server URL:

```typescript
export const API_CONFIG = {
  DEFAULT_BASE_URL: 'http://your-server:8000',
  DEFAULT_WS_URL: 'ws://your-server:8000/ws',
  // ...
};
```

Or configure it from the Settings screen in the app.

## Running the App

### Development Mode

```bash
# Start Expo dev server
npm start

# Run on iOS simulator
npm run ios

# Run on Android emulator
npm run android

# Run in web browser (for testing)
npm run web
```

### Using Expo Go (Quick Testing)

1. Install Expo Go app on your iOS/Android device
2. Run `npm start`
3. Scan the QR code with your device camera (iOS) or Expo Go app (Android)

## Building for Production

### iOS

```bash
# Build for iOS (requires Apple Developer account)
eas build --platform ios

# Or create development build
expo run:ios
```

### Android

```bash
# Build APK for Android
eas build --platform android

# Or create development build
expo run:android
```

## Project Structure

```
mobile/
├── src/
│   ├── api/                 # API client and WebSocket manager
│   │   ├── client.ts        # HTTP API client (Axios)
│   │   └── websocket.ts     # WebSocket manager with mobile optimizations
│   ├── components/          # Reusable UI components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   └── Card.tsx
│   ├── constants/           # App configuration and theme
│   │   ├── config.ts        # API URLs, timeouts, storage keys
│   │   └── theme.ts         # Colors, typography, spacing
│   ├── contexts/            # React contexts
│   │   └── AuthContext.tsx  # Authentication state management
│   ├── navigation/          # Navigation configuration
│   │   └── AppNavigator.tsx # Stack + Tab navigation
│   ├── screens/             # App screens
│   │   ├── LoginScreen.tsx
│   │   ├── EquipmentListScreen.tsx
│   │   ├── EquipmentDetailScreen.tsx
│   │   ├── AlarmsScreen.tsx
│   │   └── SettingsScreen.tsx
│   ├── types/               # TypeScript type definitions
│   │   └── api.ts           # API response types
│   └── utils/               # Utility functions (future)
├── App.tsx                  # Main app component
├── app.json                 # Expo configuration
├── package.json             # Dependencies
└── tsconfig.json            # TypeScript configuration
```

## API Integration

The mobile app communicates with LabLink server v1.0.0+ API:

### Endpoints Used

- **Authentication:**
  - `POST /api/security/login` - Username/password login
  - `POST /api/security/mfa/login` - MFA verification
  - `POST /api/security/refresh` - Token refresh
  - `GET /api/security/user/me` - Get current user

- **Equipment:**
  - `GET /api/equipment/list` - List all equipment
  - `GET /api/equipment/{id}` - Get equipment details
  - `POST /api/equipment/{id}/connect` - Connect equipment
  - `POST /api/equipment/{id}/disconnect` - Disconnect equipment
  - `POST /api/equipment/{id}/command` - Send command
  - `POST /api/equipment/{id}/query` - Query equipment

- **Alarms:**
  - `GET /api/alarms/list` - List all alarms
  - `GET /api/alarms/active` - Get active alarms
  - `POST /api/alarms/{id}/acknowledge` - Acknowledge alarm

### WebSocket Messages

- `equipment_update` - Real-time equipment status changes
- `alarm_triggered` - New alarm triggered
- `alarm_cleared` - Alarm cleared
- `data_update` - Data acquisition updates

## Security

### Authentication
- JWT access tokens stored in secure storage (Keychain on iOS, KeyStore on Android)
- Automatic token refresh before expiration
- Biometric authentication for app unlock
- MFA/2FA support

### Network Security
- All API calls use HTTPS in production
- Certificate pinning support (can be enabled)
- Secure WebSocket (WSS) for real-time data

### Data Storage
- Sensitive data stored in platform-specific secure storage
- No sensitive data in AsyncStorage
- Automatic cleanup on logout

## Configuration

### Server Settings

Users can configure server URLs from the Settings screen:

1. Open Settings tab
2. Scroll to "Server Connection"
3. Enter Server URL (e.g., `http://192.168.1.100:8000`)
4. Enter WebSocket URL (e.g., `ws://192.168.1.100:8000/ws`)
5. Tap "Save Settings"

### Biometric Authentication

1. Open Settings tab
2. Toggle "Biometric Authentication"
3. Authenticate with Face ID/Touch ID to enable

## Troubleshooting

### Connection Issues

1. **Check server URL**: Ensure the server URL in Settings is correct
2. **Network connectivity**: Verify your device can reach the server
3. **CORS**: Server must allow requests from mobile app
4. **Firewall**: Ensure ports 8000 (HTTP) and WebSocket are open

### WebSocket Disconnections

The app automatically handles reconnections with exponential backoff:
- Network changes trigger immediate reconnection
- App foreground/background transitions handled gracefully
- Max 10 reconnection attempts with up to 60s delay

### Biometric Authentication Not Available

- Ensure device supports Face ID/Touch ID
- Check that biometric authentication is configured in device settings
- Grant app permission to use biometric features

## Development

### Adding New Screens

1. Create screen component in `src/screens/`
2. Add to navigation in `src/navigation/AppNavigator.tsx`
3. Add TypeScript types if needed

### Adding New API Endpoints

1. Add types to `src/types/api.ts`
2. Add method to `src/api/client.ts`
3. Use in screen components

### Styling

All styles use the centralized theme from `src/constants/theme.ts`:

```typescript
import { Colors, Typography, Spacing } from '../constants/theme';

const styles = StyleSheet.create({
  container: {
    padding: Spacing.md,
    backgroundColor: Colors.light.background,
  },
  title: {
    fontSize: Typography.fontSize.xl,
    color: Colors.primary,
  },
});
```

## Testing

```bash
# Run tests (when implemented)
npm test

# Type checking
npx tsc --noEmit

# Linting
npx eslint src/
```

## Deployment

### App Store (iOS)

1. Configure `app.json` with bundle ID and version
2. Build with EAS: `eas build --platform ios`
3. Submit to App Store Connect
4. Review and release

### Google Play (Android)

1. Configure `app.json` with package name and version
2. Build with EAS: `eas build --platform android`
3. Upload to Google Play Console
4. Review and release

## Roadmap

### v1.1.1 (Patch)
- [ ] Push notifications for alarms
- [ ] Deep linking for OAuth callbacks
- [ ] Improved error handling

### v1.2.0 (Minor)
- [ ] Data acquisition visualization
- [ ] Waveform charts
- [ ] Offline mode with data sync
- [ ] Dark mode support

### v1.3.0 (Minor)
- [ ] Equipment profiles management
- [ ] Scheduled operations view
- [ ] Test sequences execution
- [ ] Advanced search and filters

## Contributing

This mobile app is part of the LabLink project. See the main [LabLink README](../README.md) for contribution guidelines.

## License

TBD

## Support

For issues and questions:
- GitHub Issues: https://github.com/X9X0/LabLink/issues
- Documentation: See `/docs` in main repository

---

**LabLink Mobile v1.1.0** - Built with React Native and Expo
