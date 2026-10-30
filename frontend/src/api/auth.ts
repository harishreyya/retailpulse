import { apiClient } from "./client";
import type {
  CompanyRegisterPayload, LoginPayload, RegisterResponse, TokenResponse, User,
} from "../types";

export const registerCompany = async (payload: CompanyRegisterPayload) => {
  const { data } = await apiClient.post<RegisterResponse>("/auth/register", payload);
  return data;
};

export const login = async (payload: LoginPayload) => {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", payload);
  return data;
};

export const logout = async (refreshToken: string) => {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
};

export const getProfile = async () => {
  const { data } = await apiClient.get<User>("/auth/me");
  return data;
};
