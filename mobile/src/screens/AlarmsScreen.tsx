/**
 * LabLink Mobile - Alarms Screen
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { apiClient } from '../api/client';
import { wsManager } from '../api/websocket';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import type { Alarm, AlarmSeverity, WebSocketMessage, WebSocketMessageType } from '../types/api';

export const AlarmsScreen: React.FC = () => {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'all' | 'active' | 'unacknowledged'>('all');

  useEffect(() => {
    loadAlarms();
    setupWebSocket();
  }, []);

  const setupWebSocket = () => {
    // Subscribe to alarm triggers
    const unsubscribeTrigger = wsManager.on('alarm_triggered' as WebSocketMessageType, (message: WebSocketMessage) => {
      handleAlarmTriggered(message.data);
    });

    // Subscribe to alarm clears
    const unsubscribeClear = wsManager.on('alarm_cleared' as WebSocketMessageType, (message: WebSocketMessage) => {
      handleAlarmCleared(message.data);
    });

    return () => {
      unsubscribeTrigger();
      unsubscribeClear();
    };
  };

  const handleAlarmTriggered = (alarm: Alarm) => {
    setAlarms((prev) => {
      const index = prev.findIndex((a) => a.id === alarm.id);
      if (index !== -1) {
        const updated = [...prev];
        updated[index] = alarm;
        return updated;
      }
      return [alarm, ...prev];
    });
  };

  const handleAlarmCleared = (alarmId: string) => {
    setAlarms((prev) => prev.filter((a) => a.id !== alarmId));
  };

  const loadAlarms = async () => {
    try {
      const response = await apiClient.getAlarms();
      setAlarms(response.alarms);
    } catch (error) {
      Alert.alert('Error', 'Failed to load alarms');
      console.error('Failed to load alarms:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadAlarms();
  }, []);

  const handleAcknowledge = async (alarm: Alarm) => {
    try {
      await apiClient.acknowledgeAlarm(alarm.id);
      Alert.alert('Success', 'Alarm acknowledged');
      loadAlarms();
    } catch (error: any) {
      Alert.alert('Error', error?.response?.data?.detail || 'Failed to acknowledge alarm');
    }
  };

  const getSeverityColor = (severity: AlarmSeverity): string => {
    switch (severity) {
      case 'critical':
        return Colors.alarmCritical;
      case 'error':
        return Colors.alarmError;
      case 'warning':
        return Colors.alarmWarning;
      case 'info':
        return Colors.alarmInfo;
      default:
        return Colors.light.textSecondary;
    }
  };

  const getFilteredAlarms = () => {
    switch (filter) {
      case 'active':
        return alarms.filter((a) => a.active);
      case 'unacknowledged':
        return alarms.filter((a) => !a.acknowledged);
      default:
        return alarms;
    }
  };

  const renderAlarmItem = ({ item }: { item: Alarm }) => (
    <Card style={[styles.alarmCard, { borderLeftColor: getSeverityColor(item.severity), borderLeftWidth: 4 }]}>
      <View style={styles.alarmHeader}>
        <View style={styles.alarmInfo}>
          <Text style={styles.alarmName}>{item.name}</Text>
          <View style={styles.badges}>
            <View style={[styles.badge, { backgroundColor: getSeverityColor(item.severity) }]}>
              <Text style={styles.badgeText}>{item.severity}</Text>
            </View>
            {item.active && (
              <View style={[styles.badge, { backgroundColor: Colors.error }]}>
                <Text style={styles.badgeText}>ACTIVE</Text>
              </View>
            )}
            {!item.acknowledged && (
              <View style={[styles.badge, { backgroundColor: Colors.warning }]}>
                <Text style={styles.badgeText}>NEW</Text>
              </View>
            )}
          </View>
        </View>
      </View>

      <Text style={styles.alarmMessage}>{item.message}</Text>

      {item.equipment_id && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Equipment:</Text>
          <Text style={styles.detailValue}>{item.equipment_id}</Text>
        </View>
      )}

      {item.value !== undefined && item.threshold !== undefined && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Value:</Text>
          <Text style={styles.detailValue}>
            {item.value} (threshold: {item.threshold})
          </Text>
        </View>
      )}

      {item.triggered_at && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Triggered:</Text>
          <Text style={styles.detailValue}>
            {new Date(item.triggered_at).toLocaleString()}
          </Text>
        </View>
      )}

      {item.acknowledged_at && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Acknowledged:</Text>
          <Text style={styles.detailValue}>
            {new Date(item.acknowledged_at).toLocaleString()}
            {item.acknowledged_by && ` by ${item.acknowledged_by}`}
          </Text>
        </View>
      )}

      {!item.acknowledged && (
        <Button
          title="Acknowledge"
          onPress={() => handleAcknowledge(item)}
          style={styles.acknowledgeButton}
          size="small"
        />
      )}
    </Card>
  );

  const renderHeader = () => (
    <View style={styles.header}>
      <Text style={styles.headerTitle}>Alarms</Text>
      <View style={styles.filterContainer}>
        <TouchableOpacity
          style={[styles.filterButton, filter === 'all' && styles.filterButtonActive]}
          onPress={() => setFilter('all')}
        >
          <Text style={[styles.filterText, filter === 'all' && styles.filterTextActive]}>
            All
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterButton, filter === 'active' && styles.filterButtonActive]}
          onPress={() => setFilter('active')}
        >
          <Text style={[styles.filterText, filter === 'active' && styles.filterTextActive]}>
            Active
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterButton, filter === 'unacknowledged' && styles.filterButtonActive]}
          onPress={() => setFilter('unacknowledged')}
        >
          <Text style={[styles.filterText, filter === 'unacknowledged' && styles.filterTextActive]}>
            New
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Text style={styles.emptyText}>No alarms</Text>
      <Text style={styles.emptySubtext}>
        {filter === 'all' ? 'All clear!' : `No ${filter} alarms`}
      </Text>
    </View>
  );

  const filteredAlarms = getFilteredAlarms();

  return (
    <View style={styles.container}>
      {renderHeader()}
      <FlatList
        data={filteredAlarms}
        renderItem={renderAlarmItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={!loading ? renderEmpty : null}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.light.background,
  },
  header: {
    padding: Spacing.md,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: Colors.light.border,
  },
  headerTitle: {
    fontSize: Typography.fontSize['2xl'],
    fontWeight: Typography.fontWeight.bold,
    color: Colors.light.text,
    marginBottom: Spacing.md,
  },
  filterContainer: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  filterButton: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.light.surface,
  },
  filterButtonActive: {
    backgroundColor: Colors.primary,
  },
  filterText: {
    fontSize: Typography.fontSize.sm,
    fontWeight: Typography.fontWeight.medium,
    color: Colors.light.text,
  },
  filterTextActive: {
    color: '#FFFFFF',
  },
  listContent: {
    padding: Spacing.md,
    flexGrow: 1,
  },
  alarmCard: {
    borderLeftWidth: 4,
  },
  alarmHeader: {
    marginBottom: Spacing.sm,
  },
  alarmInfo: {
    flex: 1,
  },
  alarmName: {
    fontSize: Typography.fontSize.lg,
    fontWeight: Typography.fontWeight.semibold,
    color: Colors.light.text,
    marginBottom: Spacing.xs,
  },
  badges: {
    flexDirection: 'row',
    gap: Spacing.xs,
  },
  badge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: Typography.fontSize.xs,
    fontWeight: Typography.fontWeight.medium,
    textTransform: 'uppercase',
  },
  alarmMessage: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
    marginBottom: Spacing.sm,
  },
  detailRow: {
    flexDirection: 'row',
    marginTop: Spacing.xs,
  },
  detailLabel: {
    fontSize: Typography.fontSize.sm,
    color: Colors.light.textSecondary,
    marginRight: Spacing.xs,
    fontWeight: Typography.fontWeight.medium,
  },
  detailValue: {
    flex: 1,
    fontSize: Typography.fontSize.sm,
    color: Colors.light.text,
  },
  acknowledgeButton: {
    marginTop: Spacing.md,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: Spacing['3xl'],
  },
  emptyText: {
    fontSize: Typography.fontSize.lg,
    fontWeight: Typography.fontWeight.semibold,
    color: Colors.light.textSecondary,
    marginBottom: Spacing.xs,
  },
  emptySubtext: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.textSecondary,
    textAlign: 'center',
  },
});
