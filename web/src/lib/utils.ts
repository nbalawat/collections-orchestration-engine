import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

export function formatDate(value: string): string {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatTime(value: string): string {
  if (!value) return '-';
  return new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDateTime(value: string): string {
  if (!value) return '-';
  return `${formatDate(value)} ${formatTime(value)}`;
}

export function stageBadgeColor(stage: string): string {
  const colors: Record<string, string> = {
    PRE_DELINQUENT: 'badge-blue',
    EARLY: 'badge-yellow',
    MID: 'badge-yellow',
    LATE: 'badge-red',
    SEVERE: 'badge-red',
    CURRENT: 'badge-green',
    CURED: 'badge-green',
    IDLE: 'badge-gray',
    DUNNING: 'badge-blue',
    PTP_ACTIVE: 'badge-green',
    PTP_BROKEN: 'badge-red',
    HARDSHIP_REVIEW: 'badge-purple',
    SUSPENDED: 'badge-red',
    CHARGED_OFF: 'badge-red',
  };
  return colors[stage] || 'badge-gray';
}

export function channelIcon(channel: string): string {
  const icons: Record<string, string> = {
    sms: '💬',
    email: '📧',
    voice: '📞',
    dialer: '📱',
    digital: '🖥️',
    system: '⚙️',
  };
  return icons[channel] || '📋';
}
