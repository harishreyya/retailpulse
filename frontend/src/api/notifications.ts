import { apiClient } from "./client";
import type { AppNotification, NotificationDetail, NotificationListResponse, NotificationFilters } from "../types";

export const listNotifications = async (filters: NotificationFilters = {}) => {
  const { data } = await apiClient.get<NotificationListResponse>("/notifications", { params: filters });
  return data;
};

export const getUnreadCount = async () => {
  const { data } = await apiClient.get<{ unread_count: number }>("/notifications/unread-count");
  return data.unread_count;
};

export const markNotificationRead = async (id: string) => {
  const { data } = await apiClient.patch<AppNotification>(`/notifications/${id}/read`);
  return data;
};

export const markAllNotificationsRead = async () => {
  const { data } = await apiClient.patch<{ updated_count: number }>("/notifications/read-all");
  return data;
};

export const getNotification = async (id: string) => {
  const { data } = await apiClient.get<NotificationDetail>(`/notifications/${id}`);
  return data;
};
